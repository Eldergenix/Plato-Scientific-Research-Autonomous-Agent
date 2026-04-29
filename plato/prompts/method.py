method_planner_prompt = r"""
{research_idea}

Instruction for planning:

Given these datasets, and information on the features and project idea, we want to design a methodology to implement this idea.
The goal of the task is to write a plan that will be used to generate a detailed description of the methodology that will be used to perform the research project.

- Start by requesting the *researcher* to provide reasoning  relevant to the given project idea.
- Clarify the specific hypotheses, assumptions, or questions that should be investigated.
- This can be done in multiple steps. 
- The focus should be strictly on the methods and workflow for this specific project to be performed. **Do not include** any discussion of future directions, future work, project extensions, or limitations.
- The description should be written as if it were a senior researcher explaining to her research assistant how to perform the research necessary for this project.

The final step of the plan must be entirely dedicated to writing the full Methodology description.

The only agent involved in this workflow is the researcher.

In this task we do not perform any calculations or analyses, only outline the methodology. 
"""

method_researcher_prompt = r"""
{research_idea}

Given this information, we want to design a methodology to implement this idea.
The goal of the task is to develop a detailed methodology that will be used to carry out the research project.

- You should focus on the methods for this specific project to be performed. **Do not include** any discussion of future directions, future work, project extensions, or limitations.
- The methodology description should be written as if it were a senior researcher explaining to her research assistant how to perform the project. 

The designed methodology should focus on describing the research and analysis that will be performed.

The full methodology description should be written in markdown format and include all the details of the designed methodology.
It should be roughly 500 words long.
"""