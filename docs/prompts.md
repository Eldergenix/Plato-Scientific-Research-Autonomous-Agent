# Prompts

Here are detailed some of the exact prompts employed for the agents in each of the steps in the Denario generation process. For all the prompts employed check the [source code](https://github.com/AstroPilot-AI/Denario).

## Idea

### Planner instructions

```py
--8<-- "denario/prompts/idea.py"
```

## Methods

### Planner instructions

```py
--8<-- "denario/prompts/method.py:1:21"
```

### Researcher instructions

```py
--8<-- "denario/prompts/method.py:22:"
```

## Experiment

### Planner instructions

```py
--8<-- "denario/prompts/experiment.py:1:16"
```

### Engineer instructions

```py
--8<-- "denario/prompts/experiment.py:18:34"
```

### Researcher instructions

```py
--8<-- "denario/prompts/experiment.py:36:46"
```

## Paper

We include here only a sample of the prompts used in the paper generation module, consult the complete list in `"denario/paper_agents/prompts.py`.

### Introduction

```py
--8<-- "denario/paper_agents/prompts.py:180:214"
```

### Methods

```py
--8<-- "denario/paper_agents/prompts.py:258:292"
```

### Results

```py
--8<-- "denario/paper_agents/prompts.py:295:336"
```

### Conclusions

```py
--8<-- "denario/paper_agents/prompts.py:368:407"
```

### Captions writing

```py
--8<-- "denario/paper_agents/prompts.py:410:438"
```

### Plot insertion

```py
--8<-- "denario/paper_agents/prompts.py:440:457"
```

### Clean section

```py
--8<-- "denario/paper_agents/prompts.py:494:529"
```

### References

```py
--8<-- "denario/paper_agents/prompts.py:553:585"
```

### Fix errors

```py
--8<-- "denario/paper_agents/prompts.py:614:642"
```
