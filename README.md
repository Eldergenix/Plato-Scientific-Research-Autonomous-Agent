# Plato

[![Version](https://img.shields.io/pypi/v/plato.svg)](https://pypi.python.org/pypi/plato) [![Python Version](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](https://www.python.org/downloads/) [![PyPI - Downloads](https://img.shields.io/pypi/dm/plato)](https://pypi.python.org/pypi/plato) [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/AstroPilot-AI/Plato)
<a href="https://www.youtube.com/@plato-ai" target="_blank">
<img src="https://img.shields.io/badge/YouTube-Subscribe-red?style=flat-square&logo=youtube" alt="Subscribe on YouTube" width="140"/>
</a>

Plato is a multiagent system designed to be a scientific research assistant. Plato implements AI agents with [AG2](https://ag2.ai/) and [LangGraph](https://www.langchain.com/langgraph), using [cmbagent](https://github.com/CMBAgents/cmbagent) as the research analysis backend.

## Resources

- [🌐 Project page](https://astropilot-ai.github.io/PlatoPaperPage/)

- [📄 Paper](https://arxiv.org/abs/2510.26887)

- [📖 Documentation](https://plato.readthedocs.io/en/latest/)

- [🖥️ Plato GUI repository](https://github.com/AstroPilot-AI/PlatoApp)

- [🤗 Demo web app for Plato GUI](https://huggingface.co/spaces/astropilot-ai/Plato)

- [📝 End-to-end research papers generated with Plato](https://github.com/AstroPilot-AI/PlatoExamplePapers)

- [🎥 YouTube channel](https://www.youtube.com/@plato-ai)


## Installation

To install plato create a virtual environment and pip install it. We recommend using Python 3.12:

```bash
python -m venv Plato_env
source Plato_env/bin/activate
pip install "plato[app]"
```

Or alternatively install it with [uv](https://docs.astral.sh/uv/), initializing a project and installing it:

```bash
uv init
uv add plato[app]
```

Then, run the gui with:

```
plato run
```

## Get started

Initialize a `Plato` instance and describe the data and tools to be employed.

```python
from plato import Plato

den = Plato(project_dir="project_dir")

prompt = """
Analyze the experimental data stored in data.csv using sklearn and pandas.
This data includes time-series measurements from a particle detector.
"""

den.set_data_description(prompt)
```

Generate a research idea from that data specification.

```python
den.get_idea()
```

Generate the methodology required for working on that idea.

```python
den.get_method()
```

With the methodology setup, perform the required computations and get the plots and results.

```python
den.get_results()
```

Finally, generate a latex article with the results. You can specify the journal style, in this example we choose the [APS (Physical Review Journals)](https://journals.aps.org/) style.

```python
from plato import Journal

den.get_paper(journal=Journal.APS)
```

You can also manually provide any info as a string or markdown file in an intermediate step, using the `set_idea`, `set_method` or `set_results` methods. For instance, for providing a file with the methodology developed by the user:

```python
den.set_method(path_to_the_method_file.md)
```

## Plato Dashboard (new, recommended)

A Linear-themed real-time web dashboard with full pipeline visualization, cost tracking, and live agent log streaming. See [dashboard/README.md](dashboard/README.md) for setup.

```bash
pip install "plato[dashboard]"
plato dashboard
```

The dashboard supersedes the legacy `plato run` Streamlit app for new workflows.

## PlatoApp

You can run Plato using a GUI through the [PlatoApp](https://github.com/AstroPilot-AI/PlatoApp).

The app is already installed with `pip install "plato[app]"`, otherwise install it with `pip install plato_app` or `uv sync --extra app`.

Then, launch the GUI with

```bash
plato run
```

Test a [deployed demo of the app in HugginFace Spaces](https://huggingface.co/spaces/astropilot-ai/Plato).

## Build from source

### pip

You will need python 3.12 or higher installed. Clone Plato:

```bash
git clone https://github.com/AstroPilot-AI/Plato.git
cd Plato
```

Create and activate a virtual environment

```bash
python3 -m venv Plato_env
source Plato_env/bin/activate
```

And install the project

```bash
pip install -e .
```

### uv

You can also install the project using [uv](https://docs.astral.sh/uv/), just running:

```bash
uv sync
```

which will create the virtual environment and install the dependencies and project. Activate the virtual environment if needed with

```bash
source .venv/bin/activate
```

## Docker

You can run Plato in a [Docker](https://www.docker.com/) image, which includes all the required dependencies for Plato including LaTeX. Pull the image with:

```bash
docker pull pablovd/plato:latest
```

Once built, you can run the GUI with

```bash
docker run -p 8501:8501 --rm pablovd/plato:latest
```

or in interactive mode with

```bash
docker run --rm -it pablovd/plato:latest bash
```

Share volumes with `-v $(pwd)/project:/app/project` for inputing data and accessing to it. You can also share the API keys with a `.env` file in the same folder with `-v $(pwd).env/app/.env`.

You can also build an image locally with

```bash
docker build -f docker/Dockerfile.dev -t plato_src .
```

Read more information on how to use the Docker images in the [documentation](https://plato.readthedocs.io/en/latest/docker/).

## Contributing

Pull requests are welcome! Feel free to open an issue for bugs, comments, questions and suggestions.

<!-- ## Citation

If you use this library please link this repository and cite [arXiv:2506.xxxxx](arXiv:x2506.xxxxx). -->

## Citation

If you make use of Plato, please cite the following references:

```bibtex
@article{villaescusanavarro2025platoprojectdeepknowledge,
         title={The Plato project: Deep knowledge AI agents for scientific discovery}, 
         author={Francisco Villaescusa-Navarro and Boris Bolliet and Pablo Villanueva-Domingo and Adrian E. Bayer and Aidan Acquah and Chetana Amancharla and Almog Barzilay-Siegal and Pablo Bermejo and Camille Bilodeau and Pablo Cárdenas Ramírez and Miles Cranmer and Urbano L. França and ChangHoon Hahn and Yan-Fei Jiang and Raul Jimenez and Jun-Young Lee and Antonio Lerario and Osman Mamun and Thomas Meier and Anupam A. Ojha and Pavlos Protopapas and Shimanto Roy and David N. Spergel and Pedro Tarancón-Álvarez and Ujjwal Tiwari and Matteo Viel and Digvijay Wadekar and Chi Wang and Bonny Y. Wang and Licong Xu and Yossi Yovel and Shuwen Yue and Wen-Han Zhou and Qiyao Zhu and Jiajun Zou and Íñigo Zubeldia},
         year={2025},
         eprint={2510.26887},
         archivePrefix={arXiv},
         primaryClass={cs.AI},
         url={https://arxiv.org/abs/2510.26887},
}

@software{Plato_2025,
          author = {Pablo Villanueva-Domingo, Francisco Villaescusa-Navarro, Boris Bolliet},
          title = {Plato: Modular Multi-Agent System for Scientific Research Assistance},
          year = {2025},
          url = {https://github.com/AstroPilot-AI/Plato},
          note = {Available at https://github.com/AstroPilot-AI/Plato},
          version = {latest}
          }

@software{CMBAGENT_2025,
          author = {Boris Bolliet},
          title = {CMBAGENT: Open-Source Multi-Agent System for Science},
          year = {2025},
          url = {https://github.com/CMBAgents/cmbagent},
          note = {Available at https://github.com/CMBAgents/cmbagent},
          version = {latest}
          }
```

## License

[GNU GENERAL PUBLIC LICENSE (GPLv3)](https://www.gnu.org/licenses/gpl-3.0.html)

Plato - Copyright (C) 2026 Pablo Villanueva-Domingo, Francisco Villaescusa-Navarro, Boris Bolliet

## Contact and enquiries

E-mail: [plato.astropilot.ai@gmail.com](mailto:plato.astropilot.ai@gmail.com)
