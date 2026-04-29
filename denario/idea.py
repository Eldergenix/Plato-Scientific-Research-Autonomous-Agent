import re
from pathlib import Path
import cmbagent

from .key_manager import KeyManager
from .prompts.idea import idea_planner_prompt
from .utils import create_work_dir, get_task_result

class Idea:
    """
    This class is used to develop a research project idea based on the data of interest.
    It makes use of two types of agents:

    - `idea_maker`: to generate new ideas.
    - `idea_hater`: to critique new ideas.
    
    The LLMs are provided the following instructions:

    - Ask `idea_maker` to generate 5 new research project ideas related to the datasets.
    - Ask `idea_hater` to critique these ideas.
    - Ask `idea_maker` to select and improve 2 out of the 5 research project ideas given the output of the `idea_hater`.
    - Ask `idea_hater` to critique the 2 improved ideas. 
    - Ask `idea_maker` to select the best idea out of the 2. 
    - Ask `idea_maker` to report the best idea in the form of a scientific paper title with a 5-sentence description. 

    Args:
        work_dir: working directory.
    """
    def __init__(self, 
                 keys: KeyManager,
                 work_dir: str | Path,
                 idea_maker_model = "gpt-4o", 
                 idea_hater_model = "o3-mini",
                 planner_model = "gpt-4o",
                 plan_reviewer_model = "o3-mini",
                 orchestration_model = "gpt-4.1",
                 formatter_model = "o3-mini",
                ):
        
        self.idea_maker_model = idea_maker_model
        self.idea_hater_model = idea_hater_model
        self.planner_model = planner_model
        self.plan_reviewer_model = plan_reviewer_model
        self.orchestration_model = orchestration_model
        self.formatter_model = formatter_model
        self.api_keys = keys

        self.idea_dir = create_work_dir(work_dir, "idea")

        # Set prompt
        self.planner_append_instructions = idea_planner_prompt
        
    def develop_idea(self, data_description: str) -> str:
        """
        Develops an idea based on the data description.

        Args:
            data_description: description of the data and tools to be used.
        """
        
        results = cmbagent.planning_and_control_context_carryover(data_description,
                              n_plan_reviews = 1,
                              max_plan_steps = 6,
                              idea_maker_model = self.idea_maker_model,
                              idea_hater_model = self.idea_hater_model,
                              plan_instructions=self.planner_append_instructions,
                              planner_model=self.planner_model,
                              plan_reviewer_model=self.plan_reviewer_model,
                              work_dir = self.idea_dir,
                              api_keys = self.api_keys,
                              default_llm_model = self.orchestration_model,
                              default_formatter_model = self.formatter_model
                             )

        chat_history = results['chat_history']
        
        try:
            task_result = get_task_result(chat_history,'idea_maker_nest')
        except Exception as e:
            raise e

        pattern = r'\*\*Ideas\*\*\s*\n- Idea 1:'
        replacement = "Project Idea:"
        task_result = re.sub(pattern, replacement, task_result)

        return task_result
