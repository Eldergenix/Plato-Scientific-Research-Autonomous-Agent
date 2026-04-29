# Troubleshooting

Denario can fail for many different reason. Here we describe some standard situations and how to deal with them.

## Denario failed when performing analysis with `get_results`

Denario makes use of [cmbagent](https://github.com/CMBAgents/cmbagent) as a backend for the analysis. Check carefully the logs and see what was the last stepts it was doing.

- **Failed because could not install a package**. This happens when a simple pip call to install the package does not work and additional steps are needed. In this case, we recommend trying to install manually the package and rerun this module. If manual installation is not an option, we recommend modifying the input prompt and state explicitly to do not use the package in question. After this, we recommend rerunning the entire pipeline (at least the method part) or editing manually the `.md` files to make sure there is no mention to the problematic package.

- **Failed because of timed out**. Some calculations may take longer than expected (or time allocated). In this case, one can rerun the module restarting it from the step it failed. For this, rerun denario with

```python
from denario import Denario

# Follow the research plan, write and execute code, make plots, and summarize the results
den.get_results(engineer_model='gemini-2.5-pro',
		researcher_model='gemini-2.5-pro',
		restart_at_step=2)
```

change LLM models and step according to your case.

- **Failed because could not fix bug**. Sometimes, Denario will write a piece of code that will fail. It will then try to fix the problem (sometimes just a bug). However, in some cases it will not manage to do it. Sometimes this happens in the early steps when just reading the data and doing some prepreocessing. In this case, we recommend rerunning the module from the beginning, i.e.

```python
from denario import Denario

# Follow the research plan, write and execute code, make plots, and summarize the results
den.get_results(engineer_model='gemini-2.5-pro',
		researcher_model='gemini-2.5-pro')
```

but modifying the input prompt to make a bit more clear the data, its struture, and perhaps adding a simple code to help reading the data.

- **It did not generate any plot**. Sometimes, even when performing complex numeric computations, Denario may not generate any plot at all. Editing the input data description including the requirement of generating plots usually ensures that these are created.

## Denario failed when writing the paper

This module will provide a check mark (✅ or ❌) after each section it writes. Sometimes it may fail at different parts. For instance, it may have written properly the abstract, introduction, results and conclusions, but it may have failed in the methods section. Denario will try to fix the LaTeX problems but in some cases it wont be able to do it. In this situation, we recommend identifying the problematic part (methods in this case) and go to `paper/temp/methods.tex` and erase that file. Next, rerun the module:

```python
from denario import Denario, Journal

# Write a paper with [APS (Physical Review Journals)](https://journals.aps.org/) style
den.get_paper(journal=Journal.AAS, llm='gemini-2.5-flash', add_citations=False)
```

The parts that have been already written, will just be read, while the missing parts, e.g. methods.tex, will be regenerated.

When a paper is written, it will produce several versions:

- `paper_v1_preliminary`
- `paper_v2_no_citations`
- `paper_v3_citations` (only if `add_citations=True`)
- `paper_v4_final` (only if `add_citations=True`)

We recommend checking all versions, and not just the last one, as in some cases some plots may be missing. If figures are in version1, but missing in version2, remove all the results files `paper/temp/Results*` and rerun Denario.

Sometimes Denario may have problems inserting figures in the text. In this case, as above, we recommend checking the `paper/temp` folder and removing the problematic files.

Sometimes, in the paper there may be missing parts of text (e.g. in the abstract or the main text). This sometimes happens because LaTeX takes the symbol % as a comment, while sometimes in the text is intended to be used as the percent symbol. In this case, we recommend opening the LaTeX file (e.g. `paper_v2_no_citations`.tex or `paper_v4_final.tex`) fix the error (e.g. change % by \%) and recompile again with something like:

```sh
xelatex paper_v2_no_citations.tex
xelatex paper_v2_no_citations.tex
```

or

```sh
xelatex paper_v4_final.tex
bibtex paper_v4_final
xelatex paper_v4_final.tex
xelatex paper_v4_final.tex
```

Note that at least two compilations are needed to include references properly.

## Tips

Here are some tips to have in mind when running Denario to have better results:

- **Experiment with different LLMs**. Some of them, like the `mini` OpenAI series, can be faster and adequate enough for simple tasks such as methodology generation, but usually fail when applied in engineer agents in the analysis module. Try to find the most suitable one for each task.
- **The more detail in the data description the better**. Try to provide as many details as possible about the problem to be solved and the structure and content of the data. Also consider using the `enhance_data_description` method to expand it.
- **Be explicit with the requirements**. For instance, make explicit in the input prompt if you want to generate plots, employ specific tools or libraries, consider limited GPU/CPU resources, etc.
- **Try the different cmbagent and langgraph backends**. For those modules where both implementations are available (`get_idea` and `get_method`), each backends may produce completely different results. The `cmbagent` backend involves a planning and control strategy with more agents and steps involved and in principle could provide more complex results. However, depending on the task, the faster langgraph could be enough and even provide more satisfying results. Feel free to experiment with all the options!
