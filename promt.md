
ok, we got basic ipynb. It's working, basic experiment conducted pretty well, and there is time to full scale experimenting to prove statistical meaning. 
What I'd like you to set up and mind:
1. Environment. I'd like to maintain at least 3 sources: 
	   - exp_plan.md - storage for stage-by-stage plan. For each stage: config,  input, goals, data sources and results. Also - data pipelines description, for path A (weights from the box) and path B (AutoGluon finetuning) 
	   - basic_cells.ipynb - set of working parts of pipeline (config, data fetch to cache, data preprocessing from cache, data feeding, model setup, metrics calculations, graphical results representation). When creating actual Jupyter notebook for current stage - you WILL get cell from basic_cells, not inventing them anew each time
	   - stage_X_scratch_pad.md - notes for each stage - working scratchpads.
	     please create files and add info about them into index section of Claude.md (also update rules should be mentioned for each file)
2. Experiment planning. Let's start with path A. I'd like to test predictability on 15m, 60m, 24h intervals, different context fillings, different tickers groups and test the result on different time windows. Please think on detailed experiment plan that will prove statistical meaning of results: for each step should been estimated: set of tickers/covariates, intervals, testing periods, goals. I'm mostly interested in directional winrate and quality on amplitude price movement forecasting. First try showed that first two predicted intervals show some "accordance" with real movement. So, I suggest evaluate metrics on 2- , 3- and 5 next interval predictions  
3. Auto-config and automation as a whole. The key bottleneck is your current inability to launc Jupyter in Colab without my manual actions. To speed up the process and run several experiments in parallel - please, implement auto-config with steps:
		- data fetching. To ease pressure on ISS API - please update code cell that will softly fetch all needed data according to full Path A plan and save it to cache (I'll mount my drive to save data between runtimes). 
		- All other data processing should address cache only (experiment, for prod forecasting we'll turn on API source)
		- To maintain order in things - I suggest you to update config mechanics. Let's create "config" folder with stage_X.cfg files, each with appropriate config. And update cells that loads config to get input from files. So I'll be able just put needed file into drive folder and run stage. 
		- Check that all other mechanics will work accordingly. Do we need separate .ipynbs for each stage or you could create universal one for all stages based on config files - it's up to you
4. Results representation. Each stage should be finalized with commented metrics and all plots that I could estimate "by glance"  
