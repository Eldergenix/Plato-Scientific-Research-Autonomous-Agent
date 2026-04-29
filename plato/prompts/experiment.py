experiment_planner_prompt = r"""
{research_idea}

{methodology}

Given these datasets, project idea and methodology, we want to perform the project analysis and generate the results, plots and insights.

The goal is to perform the in-depth research and analysis. 

The plan must strictly involve only the following agents: {involved_agents_str}.

The goal here is to do the in-depth research and analysis, not an exploratory data analysis.

The final step of the plan, carried out by the researcher agent, must be entirely dedicated to writting the full Results section of the paper or report. If this research project involves code implementation, this final step should report on all the qualitative and quantitative results, interpretations of the plots and key statistics, and references to the plots generated in the previous steps.
The final result report will be what will be passed on to the paper writer agents, so all relevant information must be included in the final report (everything else will be discarded).
"""

experiment_engineer_prompt = r"""
{research_idea}

{methodology}

Given these datasets, and information on the features and project idea and methodology, we want to perform the project analysis and generate the results, plots and key statistics.
The goal is to perform the in-depth research and analysis. This means that you must generate the results, plots and key statistics.

Warnings for computing and plotting: 
- make sure dynamical ranges are well captured (carefully adjust the limits, binning, and log or linear axes scales, for each feature).

For histograms (if needed):
-Use log-scale for features with values spanning several orders of magnitudes.

**GENERAL IMPORTANT INSTRUCTIONS**: You must print out in the console ALL the quantitative information that you think the researcher will need to interpret the results. (The researcher does not have access to saved data files, only to what you print out!)
Remember that the researcher agent can not load information from files, so you must print ALL necessary info in the console (without truncation). For this, it may be necessary to change pandas (if using it) display options.
"""

experiment_researcher_prompt =  r"""
{research_idea}

{methodology}

At the end of the session, your task is to generate a detailed/extensive **discussion** and **interpretation** of the results. 
If quantitative results were derived you should provide interpretations of the plots and interpretations of the key statistics, including reporting meaningful quantitative results, tables and references to matarial previously generated in the session.
The results should be reported in full (not a summary) and in academic style. The results report/section should be around 2000 words.

The final result report will be what will be passed on to the paper writer agents, so all relevant information must be included in the final report (everything else will be discarded).
"""