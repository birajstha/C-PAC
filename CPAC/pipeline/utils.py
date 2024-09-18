# Copyright (C) 2021-2024  C-PAC Developers

# This file is part of C-PAC.

# C-PAC is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.

# C-PAC is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with C-PAC. If not, see <https://www.gnu.org/licenses/>.
"""C-PAC pipeline engine utilities."""

from itertools import chain

from CPAC.func_preproc.func_motion import motion_estimate_filter
from CPAC.utils.bids_utils import insert_entity
from CPAC.utils.monitoring import IFLOGGER

MOVEMENT_FILTER_KEYS = motion_estimate_filter.outputs


def reorient_image(input_file, orientation):
    """Reorient the input image to the desired orientation. Replaces the original input_file with the reoriented image.

    Parameters
    ----------
    input_file : str
        Input image file path
    orientation : str
        Desired orientation of the input image

    Returns
    -------
    output_file : str
        Reoriented image file path
    """
    import os
    import shutil
    import subprocess

    output_file = os.path.join(
        os.getcwd(),
        f"reoriented_{os.path.basename(input_file)}",
    )
    # if output file exist delete it
    if os.path.exists(output_file):
        os.remove(output_file)

    # make a copy of the input file as temp file so that the original file is not modified
    temp_file = os.path.join(
        os.getcwd(),
        f"temp_{os.path.basename(input_file)}",
    )
    shutil.copy(input_file, temp_file)

    cmd_3drefit = ["3drefit", "-deoblique", temp_file]
    cmd_3dresample = [
        "3dresample",
        "-orient",
        orientation,
        "-prefix",
        output_file,
        "-inset",
        temp_file,
    ]
    subprocess.run(cmd_3drefit, check=True)
    subprocess.run(cmd_3dresample, check=True)

    # remove the temporary file
    os.remove(temp_file)

    return output_file


def check_orientation(input_file, desired_orientation, reorient=True):
    """Find the orientation of the input file and reorient it if necessary. Does not modify the original input file.

    Parameters
    ----------
    input_file : str
        Input file path
    desired_orientation : str
        Desired orientation of the input file
    reorient : bool
        Reorient the input file to the desired orientation

    Returns
    -------
    output_file : str
        Reoriented image file path
    """
    import subprocess

    cmd_3dinfo = ["3dinfo", "-orient", input_file]

    orientation = (
        subprocess.run(cmd_3dinfo, capture_output=True, text=True, check=False)
        .stdout.strip()
        .upper()
    )
    if orientation != desired_orientation and reorient:
        IFLOGGER.info(
            f"+++ Reorienting {input_file} from {orientation} to {desired_orientation} +++"
        )
        try:
            output_file = reorient_image(input_file, desired_orientation)
        except Exception as e:
            IFLOGGER.error(
                f"Error in reorienting the image: {input_file}.\nCould not reorient the image to {desired_orientation}"
            )
            IFLOGGER.error(f"Error: {e}")
            output_file = input_file  # return the original file ?
    else:
        IFLOGGER.info(
            f"+++ Orientation of {input_file} is already {desired_orientation} +++"
        )
        output_file = input_file
    return output_file


def name_fork(resource_idx, cfg, json_info, out_dct):
    """Create and insert entities for forkpoints.

    Parameters
    ----------
    resource_idx : str

    cfg : CPAC.utils.configuration.Configuration

    json_info : dict

    out_dct : dict

    Returns
    -------
    resource_idx : str

    out_dct : dict
    """
    if cfg.switch_is_on(
        [
            "functional_preproc",
            "motion_estimates_and_correction",
            "motion_estimate_filter",
            "run",
        ]
    ):
        filt_value = None
        _motion_variant = {
            _key: json_info["CpacVariant"][_key]
            for _key in MOVEMENT_FILTER_KEYS
            if _key in json_info.get("CpacVariant", {})
        }
        if "unfiltered-" in resource_idx:
            resource_idx = resource_idx.replace("unfiltered-", "")
            filt_value = "none"
        else:
            try:
                filt_value = next(
                    json_info["CpacVariant"][_k][0].replace(
                        "motion_estimate_filter_", ""
                    )
                    for _k, _v in _motion_variant.items()
                    if _v
                )
            except (IndexError, KeyError):
                filt_value = "none"
        resource_idx, out_dct = _update_resource_idx(
            resource_idx, out_dct, "filt", filt_value
        )
    if cfg.switch_is_on(["nuisance_corrections", "2-nuisance_regression", "run"]):
        variants = [
            variant.split("_")[-1]
            for variant in chain.from_iterable(
                json_info.get("CpacVariant", {}).values()
            )
            if variant.startswith("nuisance_regressors_generation")
        ]
        if cfg.switch_is_off(["nuisance_corrections", "2-nuisance_regression", "run"]):
            variants.append("Off")
        reg_value = variants[0] if variants else None
        resource_idx, out_dct = _update_resource_idx(
            resource_idx, out_dct, "reg", reg_value
        )
    return resource_idx, out_dct


def present_outputs(outputs: dict, keys: list) -> dict:
    """
    Return the subset of ``outputs`` including only that are present in ``keys``.

    I.e., :py:func:`~CPAC.func_preproc.func_motion.motion_correct_connections`
    will have different items in its ``outputs`` dictionary at different
    times depending on the ``motion_correction`` configuration;
    :py:func:`~CPAC.func_preproc.func_motion.func_motion_estimates` can
    then wrap that ``outputs`` in this function and provide a list of
    keys of the desired outputs to include, if they are present in the
    provided ``outputs`` dictionary, eliminating the need for multiple
    NodeBlocks that differ only by configuration options and relevant
    output keys.

    Parameters
    ----------
    outputs : dict

    keys : list of str

    Returns
    -------
    dict
        outputs filtered down to keys

    Examples
    --------
    >>> present_outputs({'a': 1, 'b': 2, 'c': 3}, ['b'])
    {'b': 2}
    >>> present_outputs({'a': 1, 'b': 2, 'c': 3}, ['d'])
    {}
    >>> present_outputs({'a': 1, 'b': 2, 'c': 3}, ['a', 'c'])
    {'a': 1, 'c': 3}
    """  # pylint: disable=line-too-long
    return {key: outputs[key] for key in keys if key in outputs}


def source_set(sources: str | list | set) -> set:
    """Given a CpacProvenance, return a set of {resource}:{source} strings.

    Parameters
    ----------
    sources: str, list, or set

    Returns
    -------
    set

    Examples
    --------
    >>> source_set([[[['bold:func_ingress',
    ...       'desc-preproc_bold:func_reorient',
    ...       'desc-preproc_bold:func_truncate'],
    ...      ['TR:func_metadata_ingress'],
    ...      ['tpattern:func_metadata_ingress'],
    ...      'desc-preproc_bold:func_slice_time'],
    ...     [['bold:func_ingress',
    ...       'desc-preproc_bold:func_reorient',
    ...       'desc-preproc_bold:func_truncate'],
    ...      ['bold:func_ingress', 'desc-reorient_bold:func_reorient'],
    ...      'motion-basefile:get_motion_ref_fmriprep_reference'],
    ...     'desc-preproc_bold:motion_correction_only_mcflirt'],
    ...         [[['bold:func_ingress',
    ...           'desc-preproc_bold:func_reorient',
    ...           'desc-preproc_bold:func_truncate'],
    ...      ['bold:func_ingress', 'desc-reorient_bold:func_reorient'],
    ...      'motion-basefile:get_motion_ref_fmriprep_reference'],
    ...     [[['bold:func_ingress',
    ...        'desc-preproc_bold:func_reorient',
    ...        'desc-preproc_bold:func_truncate'],
    ...       ['TR:func_metadata_ingress'],
    ...       ['tpattern:func_metadata_ingress'],
    ...       'desc-preproc_bold:func_slice_time'],
    ...      [['bold:func_ingress',
    ...        'desc-preproc_bold:func_reorient',
    ...        'desc-preproc_bold:func_truncate'],
    ...       ['bold:func_ingress', 'desc-reorient_bold:func_reorient'],
    ...       'motion-basefile:get_motion_ref_fmriprep_reference'],
    ...      'desc-preproc_bold:motion_correction_only_mcflirt'],
    ...     ['FSL-AFNI-bold-ref:template_resample'],
    ...     ['FSL-AFNI-brain-mask:template_resample'],
    ...     ['FSL-AFNI-brain-probseg:template_resample'],
    ...     'space-bold_desc-brain_mask:bold_mask_fsl_afni'],
    ...     'desc-preproc_bold:bold_masking']) == set({
    ...     'FSL-AFNI-bold-ref:template_resample',
    ...     'FSL-AFNI-brain-mask:template_resample',
    ...     'FSL-AFNI-brain-probseg:template_resample',
    ...     'TR:func_metadata_ingress',
    ...     'bold:func_ingress',
    ...     'desc-preproc_bold:bold_masking',
    ...     'desc-preproc_bold:func_reorient',
    ...     'desc-preproc_bold:func_slice_time',
    ...     'desc-preproc_bold:func_truncate',
    ...     'desc-preproc_bold:motion_correction_only_mcflirt',
    ...     'desc-reorient_bold:func_reorient',
    ...     'motion-basefile:get_motion_ref_fmriprep_reference',
    ...     'space-bold_desc-brain_mask:bold_mask_fsl_afni',
    ...     'tpattern:func_metadata_ingress'})
    True
    """
    _set = set()
    if isinstance(sources, str):
        _set.add(sources)
    if isinstance(sources, (set, list)):
        for item in sources:
            _set.update(source_set(item))
    return _set


def _update_resource_idx(resource_idx, out_dct, key, value):
    """
    Given a resource_idx and an out_dct, insert fork-based keys as appropriate.

    Parameters
    ----------
    resource_idx : str

    out_dct : dict

    key : str

    value : str

    Returns
    -------
    resource_idx : str

    out_dct : dict
    """
    if value is not None:
        resource_idx = insert_entity(resource_idx, key, value)
        out_dct["filename"] = insert_entity(out_dct["filename"], key, value)
    return resource_idx, out_dct
