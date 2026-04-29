from typing_extensions import TypedDict, Any
from typing import Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from ..key_manager import KeyManager


# Class for Input/Output files
class FILES(TypedDict):
    Folder: str           #project folder
    data_description: str #name of the file with the data description
    LLM_calls: str        #name of the file with the calls to the LLM
    Temp: str             #name of the folder with the temporary LaTeX files
    idea: str             #name of the file to write the final idea
    methods: str          #name of the file to write the methods
    idea_log: str         #name of the file to write generated ideas and critics
    literature: str       #name of the file to write literature results
    literature_log: str   #name of the file to write literature search logs
    papers: str           #name of the file with the papers found and processed
    referee_report: str   #name of the file with the referee report
    referee_log: str      #name of the file to write the referee logs
    paper_images:str      #name of the folder that will contain the paper images
    Error: str            #name of the error file
    module_folder: str    #name of the folder containing the results from the considered module
    f_stream: str         #name of the file to stream the results

# Token class
class TOKENS(TypedDict):
    ti: int #total input tokens
    to: int #total output tokens 
    i:  int #input tokens (just for individual calls or functions)
    o:  int #output tokens (just for individual calls or functions)

# LLM class
class LLM(TypedDict):
    model: str
    max_output_tokens: int
    llm: Any
    temperature: float
    stream_verbose: bool

# Idea class
class IDEA(TypedDict):
    iteration: int
    previous_ideas: str
    idea: str
    criticism: str
    total_iterations: int

# Reviewer class
class REFEREE(TypedDict):
    paper_version: int
    report: str
    images: list[str]

# Literature class
class LITERATURE(TypedDict):
    iteration: int
    query: str
    decision: str
    papers: str
    next_agent: str
    messages: str #this keeps tracks of all previous messages
    max_iterations: 7 #maximum number of iterations to perform when searching for papers
    num_papers: int #controls the number of papers found by semantic scholar
    
# Graph state class
class GraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    idea: IDEA
    tokens: TOKENS
    llm: LLM
    files: FILES
    keys: KeyManager
    data_description: str
    task: str
    literature: LITERATURE
    referee: REFEREE
