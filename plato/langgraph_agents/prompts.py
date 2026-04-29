from langchain_core.messages import HumanMessage


def idea_maker_prompt(state):

    return [HumanMessage(content=rf"""Your goal is to generate a groundbreaking idea for a scientific paper. Generate a original idea given the data description. If available, take into account the criticism provided by another agent about the idea. Please stick to the guidelines mentioned in the data description.

Iteration {state['idea']['iteration']}
    
Data description:
{state['data_description']}

Previous ideas:
{state['idea']['previous_ideas']}

Critisms:
{state['idea']['criticism']}

Respond in the following format:

\\begin{{IDEA}}
<IDEA>
\\end{{IDEA}}

In <IDEA>, put the idea together with its description. Try to be brief in the description. Do not explain how you have addressed any criticism.
""")]


def idea_hater_prompt(state):

    return [HumanMessage(content=rf"""Your goal is to critic an idea. You will be provided with the idea together with the initial data description used to make the idea. Be a harsh critic of the idea. Take into account feasibility, impact and any other factor you think. The goal of your criticisms is to improve the idea. If the idea is not feasible, suggest to generate a new idea. When providing your feedback, take into account the guidelines in the data description. For instance, if a detailed idea is provided there, try to stick with it.

Data description:
{state['data_description']}

Previous ideas:
{state['idea']['previous_ideas']}

Current idea:
{state['idea']['idea']}

Respond in the following format:

\\begin{{CRITIC}}
<CRITIC>
\\end{{CRITIC}}

In <CRITIC>, put your criticism to the idea. Try to be brief in the description.
""")]

def methods_fast_prompt(state):

    return [HumanMessage(content=rf"""You are provided with a data description and an idea for a scientific paper. Your task is to think about the methods to use in order to carry it out.

Follow these instructions:
- generate a detailed description of the methodology that will be used to perform the research project.
- The description should clearly outline the steps, techniques, and rationale derived from the exploratory data analysis (EDA).
- The focus should be strictly on the methods and workflow for this specific project to be performed. **do not include** any discussion of future directions, future work, project extensions, or limitations.
- The description should be written as if it were a senior researcher explaining to her research assistant how to perform the research necessary for this project.
- Just provide the methods, do not add a sentence at the beginning saying showing your thinking process


Data description:
{state['data_description']}

Idea:
{state['idea']['idea']}


Respond in this format:

\\begin{{METHODS}}
<METHODS>
\\end{{METHODS}}

In <METHODS> put the methods you have generated.
""")
    ]


# prompt to address whether an idea is novel or not
def novelty_prompt(state):

    return [HumanMessage(content=f"""You are an expert scientific research assistant. Your task is to evaluate whether a proposed idea is novel by comparing it against existing literature. Novelty is defined strictly as:

- not novel: At least one paper significantly overlaps with the idea and applies it to the same type of data.

- novel: No papers show significant overlap in both idea/methods and data, after sufficient searching.

- query: If no relevant papers are found, or evidence is insufficient, request further search with a new query.

Important rules:

- The decision in the first round must always be "query".

- If no papers are returned, or results are irrelevant, set "Decision": "query".

- In your reasoning, explicitly mention titles and URLs of the most relevant papers that influenced your decision.

- Your reasoning must be a single paragraph only (no line breaks).

- Always return valid JSON exactly in the specified format, with no additional text.

- If they query was too long or specific and didnt found papers, try to be a bit more generic

- If the query was too generic and yields many papers, try to be more specific

Context Provided

Round: {state['literature']['iteration']}/{state['literature']['max_iterations']}

Data description: {state['data_description']}

Idea: {state['idea']['idea']}

Messages from previous iterations: {state['literature']['messages']}

Papers found this round:
{state['literature']['papers']}
(If iteration = 0, no papers will be shown.)

**Respond in exactly this format**:
{{
  "Reason": "Single-paragraph reasoning about novelty, mentioning relevant papers with their titles and URLs.",
  "Decision": "novel | not novel | query",
  "Query": "If Decision = query, propose the next optimal literature search query."
}}
""")]


def novelty_reflection(round, reason, decision, previous_reasons):
    return [HumanMessage(content="""An AI agent was asked to reason whether an idea was novel or not. Below, you can find its reason and its decision. You can also see previous reasonings. Given this, determine whether the idea is novel or not. There are only three possible decisions:
1) novel: if there is enough justification in the reasoning to believe the idea is novel
2) not novel: if there is enough justification for the idea being explored in a previous work
3) query: if you need to search for more papers to make the decision
Check if the decision taken made sense given the reason. If not, you can change it. Note that an idea cant be classified as novel in the first round

**Round**: round
**Previous reasons**: {previous_reasons}
**Reason**: {reason}
**Decision**: {decision}
    
Respond in the following format:
    
```json
{{
    "Decision": "The decision made; either novel, not novel, or query"
}}
```
    """)]

def summary_literature_prompt(state):

    return [HumanMessage(content=f"""We have some data and an idea to carry out with it. We have been searching the literature to find similar papers and to determine if the idea is novel or not. Below you can find the data description, the idea, and the iterations performed. Given this, please write a summary stating why the idea can be considered novel or not not novel. In your summary include the most similar and relevant found papers and theirs links and discuss what is similar but also what is different.

**Data description**:
{state['data_description']}

**Idea**:
{state['idea']['idea']}

**Literature search iterations**:
{state['literature']['messages']}

**Respond in exactly this format**:

\\begin{{SUMMARY}}
<SUMMARY>
\\end{{SUMMARY}}

In <SUMMARY> place the summary you have generated.
""")]


def reviewer_fast_prompt(state):
    
    image_parts = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
        }
        for image_b64 in state['referee']['images']
    ]

    prompt = [
        {"type":"text", "text": """You are a scientific referee. Below, you can find a scientific paper written in latex. Your task is to read and understand the paper. Next write a detailed report about the good/interesting aspects of the paper but also bad things, failures...etc. For the bad things, please provide comments on what would be needed to do in order to improve it. Note that you may be reviewing an AI-generated paper, so the author may not be human, and keywords may be missing. No need to mention those. 

- Find all flaws in the paper 
- Find things that may not be done correctly
- Identify places where further revisions would make the paper better
- Check carefully that there is enough evidence in the paper to support the conclusions 
- If the results are not good, reason whether this is a surprising thing or just it used the wrong strategy and failed. If the latter, the paper should be consider bad. 

Try to judge whether the paper will be worth a publication or not. Give a score from 0 (a very bad paper) to 9 (an amazing paper). For bad papers, give a low score.

**Respond in exactly this format**:
\\begin{{REVIEW}}
<REVIEW>
\\end{{REVIEW}}

In <REVIEW>, put your report. 
    """}] + image_parts

    return [HumanMessage(content=prompt)]
