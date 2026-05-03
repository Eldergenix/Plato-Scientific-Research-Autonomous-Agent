from typing import List
import asyncio
import time
import os
import shutil
import warnings
from pathlib import Path
from PIL import Image
import cmbagent

from .config import DEFAUL_PROJECT_NAME, INPUT_FILES, PLOTS_FOLDER, DESCRIPTION_FILE, IDEA_FILE, METHOD_FILE, RESULTS_FILE, LITERATURE_FILE
from .research import Research
from .key_manager import KeyManager
from .llm import LLM, models
from .paper_agents.journal import Journal
from .idea import Idea
from .method import Method
from .experiment import Experiment
from .paper_agents.agents_graph import build_graph
from .utils import llm_parser, input_check, check_file_paths, in_notebook
from .langgraph_agents.agents_graph import build_lg_graph
from .domain import DomainProfile, get_domain
from .state import ManifestRecorder
from .observability import callbacks_for
from .executor import get_executor
from cmbagent import preprocess_task

class Plato:
    """
    Plato main class. Allows to set the data and tools description, generate a research idea, generate methodology and compute the results. The it can generate the latex draft of a scientific article with a given journal style from the computed results.
    
    It uses two main backends:

    - `cmbagent`,  for detailed planning and control involving numerous agents for the idea, methods and results generation.
    - `langgraph`, for faster idea and method generation, and for the paper writing.

    Args:
        input_data: Input data to be used. Employ default data if `None`.
        project_dir: Directory project. If `None`, create a `project` folder in the current directory.
        clear_project_dir: Clear all files in project directory when initializing if `True`.
    """

    def __init__(self,
                 research: Research | None = None,
                 project_dir: str | None = None,
                 clear_project_dir: bool = False,
                 domain: str | DomainProfile = "astro",
                 user_id: str | None = None,
                 ):

        if project_dir is None:
            project_dir = os.path.join( os.getcwd(), DEFAUL_PROJECT_NAME )
        if not os.path.exists(project_dir):
            os.mkdir(project_dir)

        if research is None:
            research = Research()  # Initialize with default values
        self.research = research
        self.clear_project_dir = clear_project_dir
        self.user_id = user_id
        self.domain: DomainProfile = (
            domain if isinstance(domain, DomainProfile) else get_domain(domain)
        )

        if os.path.exists(project_dir) and clear_project_dir:
            shutil.rmtree(project_dir)
            os.makedirs(project_dir, exist_ok=True)
        self.project_dir = project_dir

        self.plots_folder = os.path.join(self.project_dir, INPUT_FILES, PLOTS_FOLDER)
        # Ensure the folder exists
        os.makedirs(self.plots_folder, exist_ok=True)

        self._setup_input_files()

        # Get keys from environment if they exist
        self.keys = KeyManager()
        self.keys.get_keys_from_env()

        self.run_in_notebook = in_notebook()

        self.set_all()

    def _setup_input_files(self) -> None:
        input_files_dir = os.path.join(self.project_dir, INPUT_FILES)
        
        # If directory exists and want to clear it, remove it and all its contents
        if os.path.exists(input_files_dir) and self.clear_project_dir:
            shutil.rmtree(input_files_dir)
            
        # Create fresh input_files directory
        os.makedirs(input_files_dir, exist_ok=True)

    def reset(self) -> None:
        """Reset Research object"""

        self.research = Research()

    def _start_manifest(self, workflow: str, **fields) -> ManifestRecorder:
        """Open a new RunManifest under ``project_dir/runs/<run_id>/``."""
        recorder = ManifestRecorder.start(
            project_dir=self.project_dir,
            workflow=workflow,
            domain=self.domain.name,
            user_id=self.user_id,
        )
        if fields:
            recorder.update(**fields)
        return recorder

    #---
    # Setters
    #---

    def setter(self, field: str | None, file: str) -> str:
        """Base method for setting the content of idea, method or results."""

        if field is None:
            try:
                with open(os.path.join(self.project_dir, INPUT_FILES, file), 'r') as f:
                    field = f.read()
            except FileNotFoundError:
                raise FileNotFoundError("Please provide an input string or path to a markdown file.")

        field = input_check(field)
                
        with open(os.path.join(self.project_dir, INPUT_FILES, file), 'w') as f:
            f.write(field)

        return field

    def set_data_description(self, data_description: str | None = None) -> None:
        """
        Set the description of the data and tools to be used by the agents.

        Args:
            data_description: String or path to markdown file including the description of the tools and data. If None, assume that a `data_description.md` is present in `project_dir/input_files`.
        """

        self.research.data_description = self.setter(data_description, DESCRIPTION_FILE)

        check_file_paths(self.research.data_description)

    def set_idea(self, idea: str | None = None) -> None:
        """Manually set an idea, either directly from a string or providing the path of a markdown file with the idea."""

        self.research.idea = self.setter(idea, IDEA_FILE)

    def set_method(self, method: str | None = None) -> None:
        """Manually set methods, either directly from a string or providing the path of a markdown file with the methods."""
        
        self.research.methodology = self.setter(method, METHOD_FILE)

    def set_results(self, results: str | None = None) -> None:
        """Manually set the results, either directly from a string or providing the path of a markdown file with the results."""
        
        self.research.results = self.setter(results, RESULTS_FILE)

    def set_plots(self, plots: list[str] | list[Image.Image] | None = None) -> None:
        """Manually set the plots from their path."""

        if plots is None:
            plots = [str(p) for p in (Path(self.project_dir) / "input_files" / "Plots").glob("*.png")]

        for i, plot in enumerate(plots):
            if isinstance(plot,str):
                plot_path= Path(plot)
                img = Image.open(plot_path)
                plot_name = str(plot_path.name)
            else:
                img = plot
                plot_name = f"plot_{i}.png"
            
            img.save( os.path.join(self.project_dir, INPUT_FILES, PLOTS_FOLDER, plot_name) )

    def set_all(self) -> None:
        """Set all Research fields if present in the working directory"""

        for setter in (
            self.set_data_description,
            self.set_idea,
            self.set_method,
            self.set_results,
            self.set_plots,
        ):
            try:
                setter()
            except FileNotFoundError:
                pass

    #---
    # Printers
    #---

    def printer(self, content: str) -> None:
        """Method to show the content depending on the execution environment, whether Jupyter notebook or Python script."""

        if self.run_in_notebook:
            from IPython.display import display, Markdown
            display(Markdown(content))
        else:
            print(content)

    def show_data_description(self) -> None:
        """Show the data description set by the `set_data_description` method."""

        self.printer(self.research.data_description)

    def show_idea(self) -> None:
        """Show the provided or generated idea by the `set_idea` or `get_idea` methods."""

        self.printer(self.research.idea)

    def show_method(self) -> None:
        """Show the provided or generated methods by `set_method` or `get_method`."""

        self.printer(self.research.methodology)

    def show_results(self) -> None:
        """Show the obtained results."""

        self.printer(self.research.results)

    def show_keywords(self) -> None:
        """Show the keywords."""

        print(self.research.keywords)

        if isinstance(self.research.keywords, dict):
            # Handle dict format (AAS keywords with URLs)
            keyword_list = "\n".join(
                                [f"- [{keyword}]({self.research.keywords[keyword]})" for keyword in self.research.keywords]
                            )
        else:
            # Handle list format (UNESCO keywords)
            keyword_list = "\n".join([f"- {keyword}" for keyword in self.research.keywords])
        
        self.printer(keyword_list)

    #---
    # Generative modules
    #---

    def enhance_data_description(self,
                                 summarizer_model: str, 
                                 summarizer_response_formatter_model: str) -> None:
        """
        Enhance the data description using the preprocess_task from cmbagent.

        Args:
            summarizer_model: LLM to be used for summarization.
            summarizer_response_formatter_model: LLM to be used for formatting the summarization response.
        """

        # Check if data description exists
        if not hasattr(self.research, 'data_description') or not self.research.data_description:
            # Try to load from file if it exists
            try:
                with open(os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE), 'r') as f:
                    self.research.data_description = f.read()
            except FileNotFoundError:
                raise ValueError("No data description found. Please set a data description first before enhancing it.")

        # Get the enhanced text from preprocess_task
        enhanced_text = preprocess_task(self.research.data_description,
                                        work_dir = self.project_dir,
                                        summarizer_model = summarizer_model,
                                        summarizer_response_formatter_model = summarizer_response_formatter_model
                                        )
        
        # Debug: Check if the enhanced text is different from original
        print(f"Original text length: {len(self.research.data_description)}")
        print(f"Enhanced text length: {len(enhanced_text)}")
        print(f"Texts are different: {self.research.data_description != enhanced_text}")
        
        # If the enhanced text is the same as original, try reading from enhanced_input.md
        if self.research.data_description == enhanced_text:
            enhanced_input_path = os.path.join(self.project_dir, "enhanced_input.md")
            if os.path.exists(enhanced_input_path):
                print("Reading enhanced content from enhanced_input.md")
                with open(enhanced_input_path, 'r', encoding='utf-8') as f:
                    enhanced_text = f.read()
                print(f"Enhanced text from file length: {len(enhanced_text)}")
        
        # Update the research object with enhanced text
        self.research.data_description = enhanced_text

        # Create the input_files directory if it doesn't exist
        input_files_dir = os.path.join(self.project_dir, INPUT_FILES)
        if not os.path.exists(input_files_dir):
            os.makedirs(input_files_dir, exist_ok=True)

        # Write the enhanced text to data_description.md
        with open(os.path.join(input_files_dir, DESCRIPTION_FILE), 'w', encoding='utf-8') as f:
            f.write(enhanced_text)

        # set the enhanced text to the research object
        self.research.data_description = enhanced_text
            
        print(f"Enhanced text written to: {os.path.join(input_files_dir, DESCRIPTION_FILE)}")

    def get_idea(self,
                 mode = "fast",
                 llm: LLM | str = models["gemini-2.0-flash"],
                 idea_maker_model: LLM | str = models["gpt-4o"],
                 idea_hater_model: LLM | str = models["o3-mini"],
                 planner_model: LLM | str = models["gpt-4o"],
                 plan_reviewer_model: LLM | str = models["o3-mini"],
                 orchestration_model: LLM | str = models["gpt-4.1"],
                 formatter_model: LLM | str = models["o3-mini"],
                ) -> None:
        """Generate an idea making use of the data and tools described in `data_description.md`.

        Args:
            mode: either "fast" or "cmbagent". Fast mode uses langgraph backend and is faster but less reliable. Cmbagent mode uses cmbagent backend and is slower but more reliable.
            llm: the LLM to be used for the fast mode.
            idea_maker_model: the LLM to be used for the idea maker agent.
            idea_hater_model: the LLM to be used for the idea hater agent.
            planner_model: the LLM to be used for the planner agent.
            plan_reviewer_model: the LLM to be used for the plan reviewer agent.
            orchestration_model: the LLM to be used for the orchestration of the agents.
            formatter_model: the LLM to be used for formatting the responses of the agents.
        """

        print(f"Generating idea with {mode} mode")

        if mode == "fast":
            self.get_idea_fast(llm=llm)
        elif mode == "cmbagent":
            self.get_idea_cmagent(idea_maker_model=idea_maker_model,
                                  idea_hater_model=idea_hater_model,
                                  planner_model=planner_model,
                                  plan_reviewer_model=plan_reviewer_model,
                                  orchestration_model=orchestration_model,
                                  formatter_model=formatter_model)
        else:
            raise ValueError("Mode must be either 'fast' or 'cmbagent'")

    def get_idea_cmagent(self,
                    idea_maker_model: LLM | str = models["gpt-4o"],
                    idea_hater_model: LLM | str = models["o3-mini"],
                    planner_model: LLM | str = models["gpt-4o"],
                    plan_reviewer_model: LLM | str = models["o3-mini"],
                    orchestration_model: LLM | str = models["gpt-4.1"],
                    formatter_model: LLM | str = models["o3-mini"],
                ) -> None:
        """Generate an idea making use of the data and tools described in `data_description.md` with the cmbagent backend.

        Args:
            idea_maker_model: the LLM to be used for the idea maker agent.
            idea_hater_model: the LLM to be used for the idea hater agent.
            planner_model: the LLM to be used for the planner agent.
            plan_reviewer_model: the LLM to be used for the plan reviewer agent.
            orchestration_model: the LLM to be used for the orchestration of the agents.
            formatter_model: the LLM to be used for formatting the responses of the agents.
        """
        warnings.warn(
            "Plato.get_idea(mode='cmbagent')/get_idea_cmagent is deprecated. "
            "Use Plato.get_idea(mode='fast') (LangGraph). The cmbagent path is "
            "retained only for Plato.get_results() until a sandboxed Executor lands.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Get LLM instances
        idea_maker_model = llm_parser(idea_maker_model)
        idea_hater_model = llm_parser(idea_hater_model)
        planner_model = llm_parser(planner_model)
        plan_reviewer_model = llm_parser(plan_reviewer_model)
        orchestration_model = llm_parser(orchestration_model)
        formatter_model = llm_parser(formatter_model)
        
        if self.research.data_description == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE), 'r') as f:
                self.research.data_description = f.read()

        idea = Idea(work_dir = self.project_dir,
                    idea_maker_model = idea_maker_model.name,
                    idea_hater_model = idea_hater_model.name,
                    planner_model = planner_model.name,
                    plan_reviewer_model = plan_reviewer_model.name,
                    keys=self.keys,
                    orchestration_model = orchestration_model.name,
                    formatter_model = formatter_model.name)
        
        idea = idea.develop_idea(self.research.data_description)
        self.research.idea = idea
        # Write idea to file
        idea_path = os.path.join(self.project_dir, INPUT_FILES, IDEA_FILE)
        with open(idea_path, 'w') as f:
            f.write(idea)

        self.idea = idea

    def get_idea_fast(self,
                      llm: LLM | str = models["gemini-2.0-flash"],
                      iterations: int = 4,
                      verbose=False,
                      ) -> None:
        """
        Generate an idea using the idea maker - idea hater method.
        
        Args:
            llm: the LLM model to be used
            verbose: whether to stream the LLM response
        """

        # Start timer
        start_time = time.time()
        # Get LLM instance
        llm = llm_parser(llm)

        recorder = self._start_manifest(
            "get_idea_fast",
            models={"idea_maker": llm.name, "idea_hater": llm.name},
        )
        config = {"configurable": {"thread_id": recorder.manifest.run_id}, "recursion_limit": 100}
        config["callbacks"] = callbacks_for(recorder.manifest.run_id, recorder.manifest.workflow, recorder=recorder)

        # Build graph
        graph = build_lg_graph(mermaid_diagram=False)

        # get name of data description file
        f_data_description = os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE)

        # Initialize the state
        input_state = {
            "task": "idea_generation",
            "files":{"Folder": self.project_dir,
                     "data_description": f_data_description}, #name of project folder
            "llm": {"model": llm.name,                #name of the LLM model to use
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens,
                    "stream_verbose": verbose},
            "keys": self.keys,
            "idea": {"total_iterations": iterations},
        }

        try:
            # Run the graph
            graph.invoke(input_state, config) # type: ignore
            recorder.finish("success")
        except Exception as e:
            recorder.finish("error", error=str(e))
            raise

        # End timer and report duration in minutes and seconds
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"Idea generated in {minutes} min {seconds} sec.")

    def check_idea(self,
                   mode : str = 'semantic_scholar',
                   llm: LLM | str = models["gemini-2.5-flash"],
                   max_iterations: int = 7,
                   verbose=False) -> str:
        """
        Use Futurehouse or Semantic Scholar to check the idea against previous literature

        Args:
            mode: either 'futurehouse' or 'semantic_scholar'
            llm: the LLM model to be used
            max_iterations: maximum number of iterations to search for literature
            verbose: whether to stream the LLM response
        """

        print(f"Checking idea in literature with {mode} mode")

        if mode == 'futurehouse':
            return self.check_idea_futurehouse()

        elif mode == 'semantic_scholar':

            return self.check_idea_semantic_scholar(llm=llm, max_iterations=max_iterations, verbose=verbose)
        
        else:
            raise ValueError("Mode must be either 'futurehouse' or 'semantic_scholar'")
    
    def check_idea_futurehouse(self) -> str:
        """
        Check with the literature if an idea is original or not.
        """

        from futurehouse_client import FutureHouseClient, JobNames
        from futurehouse_client.models import (
            TaskRequest,
        )
        import os
        fhkey = os.getenv("FUTURE_HOUSE_API_KEY")

        fh_client = FutureHouseClient(
            api_key=fhkey,
        )

        check_idea_prompt = rf"""
        Has anyone worked on or explored the following idea?

        {self.research.idea}
        
        <DESIRED_RESPONSE_FORMAT>
        Answer: <yes or no>

        Related previous work: <describe previous literature on the topic>
        </DESIRED_RESPONSE_FORMAT>
        """
        task_data = TaskRequest(name=JobNames.from_string("owl"),
                                query=check_idea_prompt)
        
        task_response = fh_client.run_tasks_until_done(task_data)

        answer = task_response[0].formatted_answer # type: ignore

        ## process the answer to remove everything above </DESIRED_RESPONSE_FORMAT>
        answer = answer.split("</DESIRED_RESPONSE_FORMAT>")[1]

        # R12 — FutureHouse responses concatenate paper abstracts that
        # could carry injection payloads. Detect signals (logged) and
        # wrap the body so any downstream prompt assembly knows the
        # text is untrusted data, not instructions. The disk write
        # below stores the wrapped form so reload paths stay safe.
        from .safety import detect_injection_signals, wrap_external

        signals = detect_injection_signals(answer)
        if signals:
            print(
                f"[plato] WARNING: injection signals {signals} in FutureHouse "
                f"response; wrapping in <external> markers.",
                flush=True,
            )
        answer = wrap_external(answer, "futurehouse_response")

        # prepend " Has anyone worked on or explored the following idea?" to the answer
        answer = "Has anyone worked on or explored the following idea?\n" + answer

        ## save the response into {INPUT_FILES}/{LITERATURE_FILE}
        with open(os.path.join(self.project_dir, INPUT_FILES, LITERATURE_FILE), 'w') as f:
            f.write(answer)

        return answer

    def check_idea_semantic_scholar(self,
                        llm: LLM | str = models["gemini-2.5-flash"],
                        max_iterations: int = 7,
                        verbose=False,
                        ) -> str:
        """
        Check with the literature if an idea is original or not.

        Args:
           llm: the LLM model to be used
           max_iterations: maximum number of iterations to check the idea
           verbose: whether to stream the LLM response 
        """

        # Start timer
        start_time = time.time()
        # Get LLM instance
        llm = llm_parser(llm)

        # Build graph
        graph = build_lg_graph(mermaid_diagram=False)

        # get name of data description and idea files
        f_data_description = os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE)
        f_idea             = os.path.join(self.project_dir, INPUT_FILES, IDEA_FILE)

        recorder = self._start_manifest(
            "check_idea_semantic_scholar",
            models={"novelty": llm.name, "literature_summary": llm.name},
        )
        config = {"configurable": {"thread_id": recorder.manifest.run_id}, "recursion_limit": 100}
        config["callbacks"] = callbacks_for(recorder.manifest.run_id, recorder.manifest.workflow, recorder=recorder)

        # Phase 2 wiring: domain drives multi-source retrieval (arxiv+openalex+ads+semantic_scholar for astro)
        # Initialize the state
        input_state = {
            "task": "literature",
            "files":{"Folder": self.project_dir, #name of project folder
                     "data_description": f_data_description,
                     "idea": f_idea},
            "llm": {"model": llm.name,                #name of the LLM model to use
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens,
                    "stream_verbose": verbose},
            "keys": self.keys,
            "literature": {"max_iterations": max_iterations},
            "idea": {"total_iterations": 4},
            "domain": self.domain.name,
        }

        # Run the graph
        try:
            graph.invoke(input_state, config) # type: ignore
            recorder.finish("success")

            # End timer and report duration in minutes and seconds
            end_time = time.time()
            elapsed_time = end_time - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            print(f"Literature checked in {minutes} min {seconds} sec.")

        except Exception as e:
            recorder.finish("error", error=str(e))
            print('Plato failed to check literature')
            print(f'Error: {e}')
            return "Error occurred during literature check"

        # Read and return the generated literature content
        try:
            literature_file = os.path.join(self.project_dir, INPUT_FILES, LITERATURE_FILE)
            with open(literature_file, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Literature file not found"
        
    def get_method(self,
                   mode = "fast",
                   llm: LLM | str = models["gemini-2.0-flash"],
                   method_generator_model: LLM | str = models["gpt-4o"],
                   planner_model: LLM | str = models["gpt-4o"],
                   plan_reviewer_model: LLM | str = models["o3-mini"],
                   orchestration_model: LLM | str = models["gpt-4.1"],
                   formatter_model: LLM | str = models["o3-mini"],
                   verbose = False,
                   ) -> None:
        """
        Generate the methods to be employed making use of the data and tools described in `data_description.md` and the idea in `idea.md`.
        
        Args:
            mode: either "fast" or "cmbagent". Fast mode uses langgraph backend and is faster but less reliable. Cmbagent mode uses cmbagent backend and is slower but more reliable.
            llm: the LLM to be used for the fast mode.
            method_generator_model: (researcher) the LLM model to be used for the researcher agent.
            planner_model: the LLM model to be used for the planner agent.
            plan_reviewer_model: the LLM model to be used for the plan reviewer agent.
            orchestration_model: the LLM to be used for the orchestration of the agents.
            formatter_model: the LLM to be used for formatting the responses of the agents.
        """

        print(f"Generating methodology with {mode} mode")

        if mode == "fast":
            self.get_method_fast(llm=llm, verbose=verbose)
        elif mode == "cmbagent":
            self.get_method_cmbagent(method_generator_model=method_generator_model,
                                     planner_model=planner_model,
                                     plan_reviewer_model=plan_reviewer_model,
                                     orchestration_model=orchestration_model,
                                     formatter_model=formatter_model)
        else:
            raise ValueError("Mode must be either 'fast' or 'cmbagent'")

    def get_method_cmbagent(self,
                            method_generator_model: LLM | str = models["gpt-4o"],
                            planner_model: LLM | str = models["gpt-4o"],
                            plan_reviewer_model: LLM | str = models["o3-mini"],
                            orchestration_model: LLM | str = models["gpt-4.1"],
                            formatter_model: LLM | str = models["o3-mini"],
                            ) -> None:
        """
        Generate the methods to be employed making use of the data and tools described in `data_description.md` and the idea in `idea.md`.

        Args:
            method_generator_model: (researcher) the LLM model to be used for the researcher agent.
            planner_model: the LLM model to be used for the planner agent.
            plan_reviewer_model: the LLM model to be used for the plan reviewer agent.
            orchestration_model: the LLM to be used for the orchestration of the agents.
            formatter_model: the LLM to be used for formatting the responses of the agents.
        """
        warnings.warn(
            "Plato.get_method(mode='cmbagent')/get_method_cmbagent is deprecated. "
            "Use Plato.get_method(mode='fast') (LangGraph). The cmbagent path is "
            "retained only for Plato.get_results() until a sandboxed Executor lands.",
            DeprecationWarning,
            stacklevel=2,
        )

        if self.research.data_description == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE), 'r') as f:
                self.research.data_description = f.read()        

        if self.research.idea == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, IDEA_FILE), 'r') as f:
                self.research.idea = f.read()

        method_generator_model = llm_parser(method_generator_model)
        planner_model = llm_parser(planner_model)
        plan_reviewer_model = llm_parser(plan_reviewer_model)
        orchestration_model = llm_parser(orchestration_model)
        formatter_model = llm_parser(formatter_model)

        method = Method(self.research.idea, keys=self.keys,  
                        work_dir = self.project_dir, 
                        researcher_model=method_generator_model.name, 
                        planner_model=planner_model.name, 
                        plan_reviewer_model=plan_reviewer_model.name,
                        orchestration_model = orchestration_model.name,
                        formatter_model = formatter_model.name)
        
        methododology = method.develop_method(self.research.data_description)
        self.research.methodology = methododology

        # Write idea to file
        method_path = os.path.join(self.project_dir, INPUT_FILES, METHOD_FILE)
        with open(method_path, 'w') as f:
            f.write(methododology)

    def get_method_fast(self,
                        llm: LLM | str = models["gemini-2.0-flash"],
                        verbose=False,
                        ) -> None:
        """
        Generate the methods to be employed making use of the data and tools described in `data_description.md` and the idea in `idea.md`. Faster version get_method.
        
        Args:
           llm: the LLM model to be used
           verbose: whether to stream the LLM response
        """

        # Start timer
        start_time = time.time()
        # Get LLM instance
        llm = llm_parser(llm)

        # Build graph
        graph = build_lg_graph(mermaid_diagram=False)

        # get name of data description file and idea
        f_data_description = os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE)
        f_idea = os.path.join(self.project_dir, INPUT_FILES, IDEA_FILE)
        
        recorder = self._start_manifest(
            "get_method_fast",
            models={"methods": llm.name},
        )
        config = {"configurable": {"thread_id": recorder.manifest.run_id}, "recursion_limit": 100}
        config["callbacks"] = callbacks_for(recorder.manifest.run_id, recorder.manifest.workflow, recorder=recorder)

        # Initialize the state
        input_state = {
            "task": "methods_generation",
            "files":{"Folder": self.project_dir,              #name of project folder
                     "data_description": f_data_description,
                     "idea": f_idea},
            "llm": {"model": llm.name,                #name of the LLM model to use
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens,
                    "stream_verbose": verbose},
            "keys": self.keys,
            "idea": {"total_iterations": 4},
        }

        try:
            # Run the graph
            graph.invoke(input_state, config) # type: ignore
            recorder.finish("success")
        except Exception as e:
            recorder.finish("error", error=str(e))
            raise

        # End timer and report duration in minutes and seconds
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"Methods generated in {minutes} min {seconds} sec.")

    def get_results(self,
                    involved_agents: List[str] = ['engineer', 'researcher'],
                    engineer_model: LLM | str = models["gpt-4.1"],
                    researcher_model: LLM | str = models["o3-mini"],
                    restart_at_step: int = -1,
                    hardware_constraints: str | None = None,
                    planner_model: LLM | str = models["gpt-4o"],
                    plan_reviewer_model: LLM | str = models["o3-mini"],
                    max_n_attempts: int = 10,
                    max_n_steps: int = 6,
                    orchestration_model: LLM | str = models["gpt-4.1"],
                    formatter_model: LLM | str = models["o3-mini"],
                    executor: str | None = None,
                    ) -> None:
        """
        Compute the results making use of the methods, idea and data description.

        Args:
            involved_agents: List of agents employed to compute the results.
            engineer_model: the LLM model to be used for the engineer agent.
            researcher_model: the LLM model to be used for the researcher agent.
            restart_at_step: the step to restart the experiment.
            hardware_constraints: the hardware constraints to be used for the experiment.
            planner_model: the LLM model to be used for the planner agent.
            plan_reviewer_model: the LLM model to be used for the plan reviewer agent.
            orchestration_model: the LLM model to be used for the orchestration of the agents.
            formatter_model: the LLM model to be used for the formatting of the responses of the agents.
            max_n_attempts: the maximum number of attempts to execute code within one step if the code execution fails.
            max_n_steps: the maximum number of steps in the workflow.
            executor: name of the registered :class:`~plato.executor.Executor` to dispatch to.
                Defaults to the current ``DomainProfile.executor`` (``"cmbagent"`` for astro).
        """

        # Get LLM instances
        engineer_model = llm_parser(engineer_model)
        researcher_model = llm_parser(researcher_model)
        planner_model = llm_parser(planner_model)
        plan_reviewer_model = llm_parser(plan_reviewer_model)
        orchestration_model = llm_parser(orchestration_model)
        formatter_model = llm_parser(formatter_model)

        if self.research.data_description == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE), 'r') as f:
                self.research.data_description = f.read()

        if self.research.idea == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, IDEA_FILE), 'r') as f:
                self.research.idea = f.read()

        if self.research.methodology == "":
            with open(os.path.join(self.project_dir, INPUT_FILES, METHOD_FILE), 'r') as f:
                self.research.methodology = f.read()

        executor_name = executor if executor is not None else self.domain.executor
        executor_obj = get_executor(executor_name)

        result = asyncio.run(executor_obj.run(
            research_idea=self.research.idea,
            methodology=self.research.methodology,
            data_description=self.research.data_description,
            project_dir=self.project_dir,
            keys=self.keys,
            involved_agents=involved_agents,
            engineer_model=engineer_model.name,
            researcher_model=researcher_model.name,
            planner_model=planner_model.name,
            plan_reviewer_model=plan_reviewer_model.name,
            restart_at_step=restart_at_step,
            hardware_constraints=hardware_constraints,
            max_n_attempts=max_n_attempts,
            max_n_steps=max_n_steps,
            orchestration_model=orchestration_model.name,
            formatter_model=formatter_model.name,
        ))

        self.research.results = result.results
        self.research.plot_paths = list(result.plot_paths)

        # move plots to the plots folder in input_files/plots
        ## Clearing the folder
        if os.path.exists(self.plots_folder):
            for file in os.listdir(self.plots_folder):
                file_path = os.path.join(self.plots_folder, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        for plot_path in self.research.plot_paths:
            shutil.move(plot_path, self.plots_folder)

        # Write results to file
        results_path = os.path.join(self.project_dir, INPUT_FILES, RESULTS_FILE)
        with open(results_path, 'w') as f:
            f.write(self.research.results)
    
    def get_keywords(self, input_text: str, n_keywords: int = 5, kw_type: str = 'unesco') -> None:
        """
        Get keywords from input text using cmbagent.

        Args:
            input_text (str): Text to extract keywords from
            n_keywords (int, optional): Number of keywords to extract. Defaults to 5.
            kw_type (str, optional): Type of keywords to extract. Defaults to 'unesco'.

        Returns:
            dict: Dictionary mapping keywords to their URLs
        """
        
        keywords = cmbagent.get_keywords(input_text, n_keywords = n_keywords, kw_type = kw_type, api_keys = self.keys)
        self.research.keywords = keywords # type: ignore
        print('keywords: ', self.research.keywords)

    def get_paper(self,
                  journal: Journal = Journal.NONE,
                  llm: LLM | str = models["gemini-2.5-flash"],
                  writer: str = 'scientist',
                  cmbagent_keywords: bool = False,
                  add_citations=True,
                  max_revision_iters: int = 2,
                  ) -> None:
        """
        Generate a full paper based on the files in input_files:

            - idea.md
            - methods.md
            - results.md
            - plots

        Different journals considered

            - NONE = None : No journal, use standard latex presets with unsrt for bibliography style.
            - AAS  = "AAS" : American Astronomical Society journals, including the Astrophysical Journal.
            - APS = "APS" : Physical Review Journals from the American Physical Society, including Physical Review Letters, PRA, etc.
            - ICML = "ICML" : ICML - International Conference on Machine Learning.
            - JHEP = "JHEP" : Journal of High Energy Physics, including JHEP, JCAP, etc.
            - NeurIPS = "NeurIPS" : NeurIPS - Conference on Neural Information Processing Systems.
            - PASJ = "PASJ" : Publications of the Astronomical Society of Japan.

        Args:
            journal: Journal style. The paper generation will use the presets of the journal considered for the latex writing. Default is no journal (no specific presets).
            llm: The LLM model to be used to write the paper.
            writer: set the style and tone to write. E.g. astrophysicist, biologist, chemist
            cmbagent_keywords: whether to use CMBAgent to select the keywords
            add_citations: whether to add citations to the paper or not
            max_revision_iters: hard cap on the reviewer-panel → redraft
                loop. Each iteration runs the four reviewer axes, the
                aggregator, and at most one redraft pass; the loop stops
                early once all critiques fall below the severity floor.
                ``0`` disables revision entirely; the default of ``2``
                mirrors what the architectural plan recommends.
        """
        
        # Start timer
        start_time = time.time()
        # Get LLM instance
        llm = llm_parser(llm)

        # Build graph
        graph = build_graph(mermaid_diagram=False)

        recorder = self._start_manifest(
            "get_paper",
            models={"writer": llm.name},
            extra={"journal": str(journal), "writer_style": writer,
                   "add_citations": add_citations,
                   "cmbagent_keywords": cmbagent_keywords},
        )
        config = {"configurable": {"thread_id": recorder.manifest.run_id}, "recursion_limit": 100}
        config["callbacks"] = callbacks_for(recorder.manifest.run_id, recorder.manifest.workflow, recorder=recorder)

        # Initialize the state
        input_state = {
            "files":{"Folder": self.project_dir}, #name of project folder
            "llm": {"model": llm.name,  #name of the LLM model to use
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens},
            "paper":{"journal": journal, "add_citations": add_citations,
                     "cmbagent_keywords": cmbagent_keywords},
            "keys": self.keys,
            "writer": writer,
            # R6 — seed the revision loop's bookkeeping so the router
            # never sees an undefined ``max_iterations`` and can stop
            # exactly at the caller-supplied cap.
            "revision_state": {"iteration": 0, "max_iterations": max_revision_iters},
        }

        try:
            # Run the graph
            asyncio.run(graph.ainvoke(input_state, config)) # type: ignore
            recorder.finish("success")
        except Exception as e:
            recorder.finish("error", error=str(e))
            raise

        # End timer and report duration in minutes and seconds
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        print(f"Paper written in {minutes} min {seconds} sec.")

    def referee(self,
                llm: LLM | str = models["gemini-2.5-flash"],
                verbose=False) -> None:
        """
        Review a paper, producing a report providing feedback on the quality of the articled and aspects to be improved.

        Args:
           llm: the LLM model to be used
           verbose: whether to stream the LLM response 
        """

        # Start timer
        start_time = time.time()
        # Get LLM instance
        llm = llm_parser(llm)

        # Build graph
        graph = build_lg_graph(mermaid_diagram=False)

        # get name of data description file and referee
        f_data_description = os.path.join(self.project_dir, INPUT_FILES, DESCRIPTION_FILE)

        recorder = self._start_manifest("referee", models={"referee": llm.name})
        config = {"configurable": {"thread_id": recorder.manifest.run_id}, "recursion_limit": 100}
        config["callbacks"] = callbacks_for(recorder.manifest.run_id, recorder.manifest.workflow, recorder=recorder)

        # Initialize the state
        input_state = {
            "task": "referee",
            "files":{"Folder": self.project_dir,  #name of project folder
                     "data_description": f_data_description},
            "llm": {"model": llm.name,                #name of the LLM model to use
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens,
                    "stream_verbose": verbose},
            "keys": self.keys,
            "referee": {"paper_version": 2},
        }

        # Run the graph
        try:
            graph.invoke(input_state, config) # type: ignore
            recorder.finish("success")

            # End timer and report duration in minutes and seconds
            end_time = time.time()
            elapsed_time = end_time - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            print(f"Paper reviewed in {minutes} min {seconds} sec.")

        except FileNotFoundError as e:
            recorder.finish("error", error=str(e))
            print('Plato failed to provide a review for the paper. Ensure that a paper in the `paper` folder ex')
            print(f'Error: {e}')
        
    def research_pilot(self, data_description: str | None = None) -> None:
        """Full run of Plato. It calls the following methods sequentially:
        ```
        set_data_description(data_description)
        get_idea()
        get_method()
        get_results()
        get_paper()
        ```
        """

        self.set_data_description(data_description)
        self.get_idea()
        self.get_method()
        self.get_results()
        self.get_paper()
