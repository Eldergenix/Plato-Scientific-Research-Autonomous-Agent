# This script runs the full workflow of Denario.
# and allows specifying the LLM models to use.
# It makes use of gravitational waves data from a binary black hole merger
# This data has been preprocessed by Jay Wadekar
# Original data can be found at https://zenodo.org/records/16004263
# The 'mini' models are much cheaper than the 'pro' models.
# but their output quality can be slightly lower.
# see e.g., https://platform.openai.com/docs/pricing

import os
import urllib.request

from denario import Denario, Journal

# Function to download GW data, already preprocessed
def download_data(workdir):
    os.makedirs(f"{workdir}/data", exist_ok=True)
    csv_files = ["GW231123_IMRPhenomXO4a.csv","GW231123_NRSur7dq4.csv"]
    for file in csv_files:
        outfile = f"{workdir}/data/{file}"
        if not os.path.isfile(outfile):
            print("Downloading data to",outfile)
            url = f"https://users.flatironinstitute.org/~fvillaescusa/Denario/Astrophysics/GW/data/{file}"
            urllib.request.urlretrieve(url, outfile)

# This is one of the example projects in the examples folder.
# It investigates the properties of a recent gravitational wave detection
# called GW231123 by the LIGO and Virgo detectors (https://arxiv.org/pdf/2507.08219)
# The data description is in the input.md file.
# All the outputs are saved in the same folder.
project_dir = "GW231123"
astro_pilot = Denario(project_dir=project_dir)

# Download the data if already does not exist
download_data(project_dir)

# Set the input prompt containing the data description
# WARNING: PLEASE PROVIDE ABSOLUTE PATHS to all the data files listed in the .md file
# (otherwise this may cause hallucinations in the LLMs)
astro_pilot.set_data_description(f"{project_dir}/input.md")

# This module generates the idea to be investigated.
# get_idea() allows to employ two backends: a planning and control workflow from cmbagent or a faster method based on Langgraph
# get_idea(mode="fast") is a faster version than get_idea(mode="cmbagent") 
# but can produce results with slightly lower quality.
# same logic below for get_method()
astro_pilot.get_idea(mode="fast",llm='gpt-4.1-mini') 

# This module checks if the idea is novel or not against previous literature
astro_pilot.check_idea(llm='gpt-4.1-mini', max_iterations=7) 

# This module generates the methodology to be employed.
astro_pilot.get_method(mode="fast",llm='gpt-4.1-mini') 

# This module writes codes, executes the codes, makes plots,
#  and summarizes the results.
astro_pilot.get_results(engineer_model='gpt-4.1',
                        researcher_model='gpt-4.1-mini',
                        planner_model='gpt-4.1-mini',
                        plan_reviewer_model='gpt-4.1-mini',
                        orchestration_model='gpt-4.1-mini',
                        formatter_model='gpt-5-mini',
                        )

# Get the paper
astro_pilot.get_paper(journal=Journal.AAS, llm='gpt-4.1-mini', add_citations=False) 

# Referee the paper
astro_pilot.referee(llm='gpt-4.1-mini')
