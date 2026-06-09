# Dev Docs

## General goal

Test the predictive capability of **Chronos-2** on financial time series. The core idea is to leverage its ability to learn and forecast multiple correlated series simultaneously.

## Experiment design

1. Deploy Chronos-2 on a T4 GPU in Colab.
2. Parse MOEX data at **15-minute**, **60-minute**, and **daily** intervals for a selected group of tickers.
3. Construct covariates.
4. Prepare the dataset (train / evaluation / test splits).
5. Use returns (`P_n − P_{n−1}`) as the base target for training and prediction.
6. Fine-tune Chronos on these data and covariates, fed as a unified group.
7. Evaluate predictive performance on unseen data (test set). To reduce noise, use a sliding window over timestamps (multiple tests shifted by a fixed time interval).
