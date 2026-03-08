document.addEventListener('DOMContentLoaded', function() {

    // --- DOM Elements ---
    const historicalMonthInput = document.getElementById('historical-month');
    const historicalTradingDaysSelect = document.getElementById('historical-trading-days');
    const predictHistoricalBtn = document.getElementById('predict-historical-btn');

    const predictNextBtn = document.getElementById('predict-next-btn');
    const predictNextInfo = document.getElementById('predict-next-info');

    const rollingMonthInput = document.getElementById('rolling-month');
    const predictRollingBtn = document.getElementById('predict-rolling-btn');

    const singlePredictionResultDiv = document.getElementById('single-prediction-result');
    const rollingPredictionResultDiv = document.getElementById('rolling-prediction-result');
    const rollingPredictionChartCanvas = document.getElementById('rolling-prediction-chart');
    const rollingInfoPara = document.getElementById('rolling-info');


    const loadingIndicator = document.getElementById('loading-indicator');
    const errorMessageDiv = document.getElementById('error-message');

    let rollingChartInstance = null; // To hold the Chart.js instance

    // --- Utility Functions ---
    function showLoading() {
        loadingIndicator.style.display = 'block';
        errorMessageDiv.style.display = 'none'; // Hide previous errors
        errorMessageDiv.textContent = '';
    }

    function hideLoading() {
        loadingIndicator.style.display = 'none';
    }

    function showError(message) {
        errorMessageDiv.textContent = `Error: ${message}`;
        errorMessageDiv.style.display = 'block';
        // Optionally hide results areas
        // singlePredictionResultDiv.style.display = 'none';
        // rollingPredictionResultDiv.style.display = 'none';
    }

    function clearResults() {
        singlePredictionResultDiv.innerHTML = '<h2>Single Day Prediction</h2><p>Select an action from the left panel.</p>';
        rollingPredictionResultDiv.style.display = 'none';
        if (rollingChartInstance) {
            rollingChartInstance.destroy();
            rollingChartInstance = null;
        }
        rollingInfoPara.textContent = '';
        errorMessageDiv.style.display = 'none';
        errorMessageDiv.textContent = '';

    }

    // --- Event Listeners ---

    // Update historical trading days when month changes
    historicalMonthInput.addEventListener('change', async function() {
        const [year, month] = this.value.split('-');
        if (!year || !month) return;

        showLoading();
        clearResults(); // Clear old results/errors

        try {
            const response = await fetch(`/get_trading_days?year=${year}&month=${month}`);
            if (!response.ok) {
                 const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            historicalTradingDaysSelect.innerHTML = '<option value="">-- Select Trading Day --</option>'; // Clear existing options
            if (data.trading_days && data.trading_days.length > 0) {
                data.trading_days.forEach(day => {
                    const option = document.createElement('option');
                    option.value = day;
                    option.textContent = day;
                    historicalTradingDaysSelect.appendChild(option);
                });
            } else {
                 historicalTradingDaysSelect.innerHTML = '<option value="">-- No trading days found --</option>';
                 showError(`No trading days found for ${year}-${month}.`); // Show message if no days
            }
        } catch (error) {
            console.error("Error fetching trading days:", error);
            showError(`Failed to fetch trading days: ${error.message}`);
            historicalTradingDaysSelect.innerHTML = '<option value="">-- Error fetching days --</option>';
        } finally {
            hideLoading();
        }
    });

    // Feature 1: Predict Historical Day Button Click
    predictHistoricalBtn.addEventListener('click', async function() {
        const selectedDate = historicalTradingDaysSelect.value;
        if (!selectedDate) {
            showError("Please select a trading day.");
            return;
        }

        showLoading();
        clearResults(); // Clear previous results

        try {
            const response = await fetch('/predict_historical', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ selected_date: selectedDate }),
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || `HTTP error! status: ${response.status}`);
            }

             // Update the single prediction result area
             singlePredictionResultDiv.innerHTML = `
                <h2>Historical Prediction Result</h2>
                <p><strong>Selected Date:</strong> ${result.target_date}</p>
                <p><strong>Predicted Closing Price:</strong> ${result.predicted_price !== undefined ? result.predicted_price : 'Error'}</p>
                <p><strong>Actual Closing Price:</strong> ${result.actual_price !== undefined ? result.actual_price : 'N/A'}</p>
                ${result.actual_price !== 'N/A' && result.predicted_price !== undefined ?
                    `<p><strong>Difference:</strong> ${(result.predicted_price - result.actual_price).toFixed(2)}</p>` : ''
                 }
            `;
             singlePredictionResultDiv.style.display = 'block'; // Ensure it's visible


        } catch (error) {
            console.error("Error predicting historical date:", error);
            showError(`Prediction failed: ${error.message}`);
             singlePredictionResultDiv.innerHTML = '<h2>Historical Prediction Result</h2><p>Prediction failed.</p>'; // Show failure in results
             singlePredictionResultDiv.style.display = 'block'; // Ensure it's visible

        } finally {
            hideLoading();
        }
    });

    // Feature 2: Predict Next Day Button Click
    predictNextBtn.addEventListener('click', async function() {
        showLoading();
        clearResults();

        try {
            const response = await fetch('/predict_next', {
                method: 'POST', // Even if no body, use POST as defined in Flask
                 headers: {
                    'Content-Type': 'application/json', // Good practice
                },
                // No body needed for this request as per current app.py
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || `HTTP error! status: ${response.status}`);
            }

             // Update the single prediction result area
            singlePredictionResultDiv.innerHTML = `
                <h2>Next Trading Day Prediction</h2>
                <p>(Based on data available up to ${result.based_on_data_up_to})</p>
                <p><strong>Predicted Closing Price for Next Trading Day:</strong> ${result.predicted_price !== undefined ? result.predicted_price : 'Error'}</p>
                <p><em>Note: Actual next trading day and price are not yet known.</em></p>
            `;
            singlePredictionResultDiv.style.display = 'block'; // Ensure it's visible


        } catch (error) {
            console.error("Error predicting next day:", error);
            showError(`Prediction failed: ${error.message}`);
             singlePredictionResultDiv.innerHTML = '<h2>Next Trading Day Prediction</h2><p>Prediction failed.</p>';
             singlePredictionResultDiv.style.display = 'block';

        } finally {
            hideLoading();
        }
    });

    // Feature 3: Run Rolling Prediction Button Click
    predictRollingBtn.addEventListener('click', async function() {
        const monthYear = rollingMonthInput.value;
        if (!monthYear) {
            showError("Please select a month for rolling prediction.");
            return;
        }

        showLoading();
        clearResults();

        try {
            const response = await fetch('/predict_month_rolling', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ month_year: monthYear }),
            });

             const result = await response.json(); // Always try to parse JSON

            if (!response.ok) {
                 throw new Error(result.error || `HTTP error! status: ${response.status}`); // Use error from JSON if available
            }


            if (result.error) { // Check for logical errors returned in JSON body even with 200 OK
                 throw new Error(result.error);
            }

            // --- Render Chart ---
            rollingPredictionResultDiv.style.display = 'block'; // Show the chart container
             rollingInfoPara.textContent = `Showing rolling predictions for ${monthYear} (starting after the 10th trading day).`;


            if (rollingChartInstance) {
                rollingChartInstance.destroy(); // Destroy previous chart if exists
            }

            const ctx = rollingPredictionChartCanvas.getContext('2d');
            rollingChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: result.labels, // Dates from backend
                    datasets: [{
                        label: 'Actual Closing Price',
                        data: result.actual,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1,
                        spanGaps: true // Connect lines over null data points if any
                    }, {
                        label: 'Predicted Closing Price',
                        data: result.predicted,
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        tension: 0.1,
                        spanGaps: true // Connect lines over null data points if any
                    }]
                },
                options: {
                     responsive: true,
                     maintainAspectRatio: false, // Allow chart to fill container
                     scales: {
                          x: {
                             type: 'time',
                             time: {
                                 unit: 'day',
                                  tooltipFormat: 'yyyy-MM-dd', // Luxon format for tooltips
                                  displayFormats: {
                                      day: 'yyyy-MM-dd' // Luxon format for display
                                  }
                             },
                            title: {
                                display: true,
                                text: 'Date'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Closing Price'
                            },
                             beginAtZero: false // Adjust based on price range
                        }
                    },
                     plugins: {
                        legend: {
                            position: 'top',
                        },
                        tooltip: {
                             mode: 'index',
                             intersect: false,
                         },
                        title: {
                            display: true,
                            text: `NIFTY50 Rolling Prediction vs Actual (${monthYear})`
                        }
                    },
                    interaction: { // Enhance tooltip interaction
                       mode: 'nearest',
                       axis: 'x',
                       intersect: false
                    }
                }
            });

        } catch (error) {
            console.error("Error running rolling prediction:", error);
            showError(`Rolling prediction failed: ${error.message}`);
            rollingPredictionResultDiv.style.display = 'block'; // Show container even on error
            rollingInfoPara.textContent = 'Rolling prediction failed to generate.';
        } finally {
            hideLoading();
        }
    });

    // Trigger change on historical month input initially to load current month's days
    // Or ensure Flask pre-populates it correctly using initial_trading_days
    if (historicalTradingDaysSelect.options.length <= 1) { // Only has the placeholder
        historicalMonthInput.dispatchEvent(new Event('change'));
    }


}); // End DOMContentLoaded