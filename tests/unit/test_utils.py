import warnings

import pytest

from plato.utils import check_file_paths


def test_check_file_paths_allows_hosted_no_dataset_sentinel():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_file_paths(
            "No dataset has been uploaded yet.\n\nGenerate a literature-first idea."
        )


def test_check_file_paths_still_warns_when_data_description_has_no_paths():
    with pytest.warns(UserWarning, match="No data files paths were found"):
        check_file_paths("Use the uploaded observations for analysis.")
