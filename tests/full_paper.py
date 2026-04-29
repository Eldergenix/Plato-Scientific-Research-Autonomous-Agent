from denario import Denario, Journal

den = Denario()

data_description = r"""
Write a short paper on harmonic oscillators. Generate several plots. Generate some data, which should not take more than 3 minutes to generate. 
"""

den.set_data_description(data_description = data_description)
den.show_data_description()

den.get_idea()
den.show_idea()

den.get_method()
den.show_method()

den.get_results()
den.show_results()

den.get_paper(journal=Journal.APS)