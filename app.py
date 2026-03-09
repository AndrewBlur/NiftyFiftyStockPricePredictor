from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import joblib
import tensorflow as tf
import numpy as np
from tensorflow.keras.layers import Layer
import yfinance as yf
from datetime import datetime, timedelta

import calendar
import pandas as pd
import concurrent.futures

class ExpandDims(Layer):
    def __init__(self, axis=-1, **kwargs):
        super().__init__(**kwargs)
        self.axis = axis

    def call(self, inputs):
        return tf.expand_dims(inputs, axis=self.axis)

    def compute_output_shape(self, input_shape):
        return input_shape + (1,)

# ---- Load Models Globally ----
modeltag = '5'
print("Loading models into memory...")
GLOBAL_SCALER = joblib.load(f'Model/RobustScaler[{modeltag}].save')

GLOBAL_MODEL_10 = tf.keras.models.load_model(f'Model/model[10,RS,{modeltag}].keras',
                                      custom_objects={'ExpandDims': ExpandDims})
GLOBAL_MODEL_6 = tf.keras.models.load_model(f'Model/model[6,RS,{modeltag}].keras',
                                     custom_objects={'ExpandDims': ExpandDims})
GLOBAL_MODEL_3 = tf.keras.models.load_model(f'Model/model[3,RS,{modeltag}].keras',
                                     custom_objects={'ExpandDims': ExpandDims})
print("Models loaded successfully.")
# ------------------------------

def get_nifty_data(start_date, end_date, required_days=10):
    nifty50 = "^NSEI"
    df = yf.download(nifty50, start=start_date, end=end_date, auto_adjust=False)
    
    if df.empty:
        trading_days = []
    else:
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        trading_days = df.index.strftime('%Y-%m-%d').tolist()

    if len(trading_days) < required_days:
        additional_days = required_days - len(trading_days)
        new_start_date = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=additional_days * 2)).strftime("%Y-%m-%d")
        df = yf.download(nifty50, start=new_start_date, end=end_date, auto_adjust=False)
        
    if not df.empty and not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df

def get_trading_days_in_month(year, month):
    # Get first and last day of the month
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    # Format dates for yfinance
    start_date = first_day.strftime("%Y-%m-%d")
    end_date = last_day.strftime("%Y-%m-%d")

    # Get NIFTY data for the month
    df = yf.download("^NSEI", start=start_date, end=end_date, auto_adjust=False)

    if df.empty:
        return [], {}

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # Return trading days and closing prices
    trading_days = df.index.strftime('%Y-%m-%d').tolist()
    # Cast each date to Timestamp to ensure .strftime works
    closing_prices = {
        pd.to_datetime(date).strftime('%Y-%m-%d'): price
        for date, price in df['Close'].items()
        if isinstance(date, (pd.Timestamp, datetime))
    }

    return trading_days, closing_prices


def get_previous_trading_days(date_str, num_days=10):
    # Convert string to datetime
    target_date = datetime.strptime(date_str, "%Y-%m-%d")

    # Calculate a start date that's likely to include enough trading days
    start_date = (target_date - timedelta(days=num_days * 2)).strftime("%Y-%m-%d")
    end_date = date_str

    # Get data
    df = yf.download("^NSEI", start=start_date, end=end_date, auto_adjust=False)

    # Get the last n trading days
    if len(df) >= num_days:
        df = df.iloc[-num_days:]

    # Use .values.tolist() to convert the Series to a list
    return df['Close'].values.tolist()


def predict_next_price(closing_prices, scaler=GLOBAL_SCALER, 
                       model_10=GLOBAL_MODEL_10, model_6=GLOBAL_MODEL_6, model_3=GLOBAL_MODEL_3):
    closing_prices = np.array(closing_prices).reshape(-1, 1)
    closing_prices_scaled = scaler.transform(closing_prices).flatten()

    X_10 = closing_prices_scaled[-10:].reshape(1, 10) if len(closing_prices_scaled) >= 10 else None
    X_6 = closing_prices_scaled[-6:].reshape(1, 6) if len(closing_prices_scaled) >= 6 else None
    X_3 = closing_prices_scaled[-3:].reshape(1, 3) if len(closing_prices_scaled) >= 3 else None

    predictions = []
    if X_10 is not None:
        pred_10_scaled = model_10(X_10, training=False).numpy()[0][0]
        predictions.append(pred_10_scaled)
    if X_6 is not None:
        pred_6_scaled = model_6(X_6, training=False).numpy()[0][0]
        predictions.append(pred_6_scaled)
    if X_3 is not None:
        pred_3_scaled = model_3(X_3, training=False).numpy()[0][0]
        predictions.append(pred_3_scaled)

    if not predictions:
        return None

    avg_pred_scaled = np.mean(predictions)
    avg_pred_unscaled = scaler.inverse_transform([[avg_pred_scaled]])[0][0]
    return avg_pred_unscaled

def is_market_hours():
    now = datetime.now()
    ist_hour = (now.hour + 5) % 24
    ist_minute = (now.minute + 30) % 60
    is_weekday = now.weekday() < 5
    is_trading_time = (10 <= ist_hour < 15) or (ist_hour == 15 and ist_minute == 0)
    return is_weekday and is_trading_time

def perform_rolling_predictions(start_date, end_date, scaler):
    """Perform rolling predictions for each trading day in the range"""
    df = get_nifty_data(start_date, end_date)

    # Need at least 11 days of data (10 for input, 1 for prediction)
    if len(df) <= 11:
        return {"error": "Not enough data for rolling predictions"}

    actual_prices = []
    predicted_prices = []
    dates = []

    for i in range(10, len(df)):
        # Convert the 10-day window to a list of floats
        input_data = df['Close'].iloc[i - 10:i].values.tolist()
        # Extract the actual price for the current day and convert to float
        actual_price = float(df['Close'].iloc[i])
        # Format the current date as a string
        current_date = df.index[i].strftime('%Y-%m-%d')

        # Make prediction (ensure the returned value is a scalar float)
        prediction = predict_next_price(input_data)
        if prediction is not None:
            prediction = float(prediction)

        actual_prices.append(actual_price)
        predicted_prices.append(prediction)
        dates.append(current_date)

    # Ensure all numbers are native Python types before jsonify
    actual_prices = [float(x) for x in actual_prices]
    predicted_prices = [float(x) if x is not None else None for x in predicted_prices]

    return {
        "dates": dates,
        "actual": actual_prices,
        "predicted": predicted_prices
    }

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    today = datetime.now()
    year = today.year
    month = today.month
    trading_days, closing_prices = get_trading_days_in_month(year, month)
    month_name = calendar.month_name[month]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "trading_days": trading_days,
        "current_month": f"{month_name} {year}",
        "year": year,
        "month": month,
        "current_date": today.strftime('%Y-%m-%d'),
        "stock_data": {},
        "predicted_price": None,
        "actual_price": None
    })

@app.post("/get_month_data")
def get_month_data(year: int = Form(...), month: int = Form(...)):
    trading_days, closing_prices = get_trading_days_in_month(year, month)
    month_name = calendar.month_name[month]
    return {
        "trading_days": trading_days,
        "closing_prices": closing_prices,
        "month_display": f"{month_name} {year}"
    }


@app.post("/predict_historical")
def predict_historical(selected_date: str = Form(...)):
    # Convert selected_date to datetime for calculations
    date_obj = datetime.strptime(selected_date, "%Y-%m-%d")

    # Get previous 10 trading days before the selected date
    closing_prices = get_previous_trading_days(selected_date)
    if len(closing_prices) < 10:
        return JSONResponse(status_code=400, content={
            "error": "Not enough historical data available for prediction"
        })

    # Make prediction
    predicted_price = predict_next_price(closing_prices)

    # Get the actual price for the selected date (using next day to capture the market close)
    end_date = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download("^NSEI", start=selected_date, end=end_date, auto_adjust=False)

    # Use .iloc[0] to safely access the first closing price and convert to float
    actual_price = float(df['Close'].iloc[0]) if not df.empty else None

    return {
        "selected_date": selected_date,
        "predicted_price": round(predicted_price, 2) if predicted_price else None,
        "actual_price": round(actual_price, 2) if actual_price is not None else None,
        "difference": round(predicted_price - actual_price, 2) if predicted_price and actual_price is not None else None
    }


@app.get("/predict_current")
def predict_current():
    today = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    next_day_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Asynchronous Data Fetching
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_df = executor.submit(yf.download, "^NSEI", start=start_date, end=today, auto_adjust=False)
        future_today = executor.submit(yf.download, "^NSEI", start=today, end=next_day_str, auto_adjust=False)

        df = future_df.result()
        today_data = future_today.result()

    if len(df) < 10:
        return JSONResponse(status_code=400, content={
            "error": "Not enough historical data available for prediction"
        })

    closing_prices = df['Close'].values.tolist()  # ensures a list of numbers
    is_open = is_market_hours()

    predicted_price = predict_next_price(closing_prices)
    actual_price = float(today_data['Close'].iloc[0]) if not today_data.empty else None

    # Ensure predicted_price is converted to a float
    predicted_price = float(predicted_price) if predicted_price is not None else None

    difference = float(
        round(predicted_price - actual_price, 2)) if predicted_price is not None and actual_price is not None else None

    return {
        "date": today,
        "predicted_price": round(predicted_price, 2) if predicted_price is not None else None,
        "actual_price": round(actual_price, 2) if actual_price is not None else None,
        "market_status": "open" if is_open else "closed",
        "difference": difference
    }

@app.post("/rolling_prediction")
def rolling_prediction(start_date: str = Form(...), end_date: str = Form(...)):
    df = get_nifty_data(start_date, end_date)
    if len(df) < 10:
        return JSONResponse(status_code=400, content={
            "error": "Selected date range does not contain enough trading days"
        })
    results = perform_rolling_predictions(start_date, end_date, GLOBAL_SCALER)
    return results
