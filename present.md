# Goal

present our experiment for new colleague, who is quite far from trading and AI thematics, but got powerful background in math.

# ToDo

please, bases on: experiment docs, chronos-2 papers, CatBoost data, our ipynbs and current state/results
describe:
- General goal
- why CatBoost and Chronos-2
- Choice of Chronos-2
- Experiment plans, our success metrics/estimations for experiment parts A & B
- Planning approach to finetune on part B (periods, approach to form training datasets with charachteristical values, hyperparams aproach, etc.)
- Key success/failure decision points - when, where and what to look

# Guidelines:

Goal - create auto-trading bot based on Chronos-2 model (already chosen), that will produce some margin (30+% YRR as a goal), including risk-management via LLM, and implementing trading strategy based on Chronos-2 forecasting via LLM

some words on problem - high concurrency and hardware requirements in HTF, lack of possibility to got market inefficiences in classical algotrading, Fine-tuned Chronos as a way to cathc current market stat inefficiences (tune on last 3 months as a try)

some words on Chronos-2 - advantages, current proven results (links on papers), what to leverage when catching market inefficitnces (where to look, what to load into, detailed proposals)

general architecture - Chronos-2 as forecast machine, what to forecast, levels of assurance, which probability will be enough for revenue, relations with comissions size. LLM as trade strategy executor, validator of foresasting, regular "uptune to current market" supervisor; separate LLM as news-risk-managemet agent

Describe of current experiment on Chronos as forecaster  -  goals, stages, general description, where to look in docs.

Planned continuation in case positive results in Chronos forecast. 


# Report style

It should be text presentation (add graphical info if needed for clarification), put results in pr.md file

# issues

If you'll need any additional info - feel free to ask.
