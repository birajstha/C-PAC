"""`Generate eXtensible Connectivity Pipeline-style quality control files <https://fcp-indi.github.io/docs/user/xcpqc>`_

Columns
-------
sub : str
    subject label :cite:`cite-BIDS21`
ses : str
    session label :cite:`cite-BIDS21`
task : str
    task label :cite:`cite-BIDS21`
run : int
    run index :cite:`cite-BIDS21`
desc : str
    description :cite:`cite-BIDS21`
space : str
    space label :cite:`cite-BIDS21`
meanFD : float
    mean Jenkinson framewise displacement :cite:`cite-Jenk02` :func:`CPAC.generate_motion_statistics.calculate_FD_J`
relMeansRMSMotion : float
    "mean value of RMS motion" :cite:`cite-Ciri19`
relMaxRMSMotion : float
    "maximum vaue of RMS motion" :cite:`cite-Ciri19`
meanDVInit : float
    "mean DVARS" :cite:`cite-Ciri19`
meanDVFinal : float
    "mean DVARS" :cite:`cite-Ciri19`
nVolCensored : int
    "total number of volume(s) censored :cite:`cite-Ciri19`
nVolsRemoved : int
    number of volumes in derivative minus number of volumes in original
    functional scan
motionDVCorrInit : float
    "correlation of RMS and DVARS before regresion" :cite:`cite-Ciri19`
motionDVCorrFinal : float
    "correlation of RMS and DVARS after regresion" :cite:`cite-Ciri19`
coregDice : float
    "Coregsitration of Functional and T1w:[…] Dice index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
coregJaccard : float
    "Coregsitration of Functional and T1w:[…] Jaccard index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
coregCrossCorr : float
    "Coregsitration of Functional and T1w:[…] cross correlation" :cite:`cite-Ciri19` :cite:`cite-Penn19`
coregCoverag : float
    "Coregsitration of Functional and T1w:[…] Coverage index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
normDice : float
    "Normalization of T1w/Functional to Template:[…] Dice index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
normJaccard : float
    "Normalization of T1w/Functional to Template:[…] Jaccard index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
normCrossCorr : float
    "Normalization of T1w/Functional to Template:[…] cross correlation" :cite:`cite-Ciri19` :cite:`cite-Penn19`
normCoverage : float
    "Normalization of T1w/Functional to Template:[…] Coverage index" :cite:`cite-Ciri19` :cite:`cite-Penn19`
"""  # noqa E501  # pylint: disable=line-too-long
import os
import re
from io import BufferedReader

import nibabel as nb
import numpy as np
import pandas as pd
from CPAC.generate_motion_statistics.generate_motion_statistics import \
    motion_power_statistics
from CPAC.pipeline import nipype_pipeline_engine as pe
from CPAC.pipeline.engine import NodeData
from CPAC.utils.interfaces.function import Function
from CPAC.utils.utils import check_prov_for_motion_tool


def dvcorr(dvars, fdj):
    """Function to correlate DVARS and FD-J"""
    dvars = np.loadtxt(dvars)
    fdj = np.loadtxt(fdj)
    if len(dvars) != len(fdj) - 1:
        raise ValueError(
            'len(DVARS) should be 1 less than len(FDJ), but their respective '
            f'lengths are {len(dvars)} and {len(fdj)}.'
        )
    return np.corrcoef(dvars, fdj[1:])[0, 1]


def strings_from_bids(final_func):
    """
    Function to gather BIDS entities into a dictionary

    Parameters
    ----------
    final_func : str

    Returns
    -------
    dict

    Examples
    --------
    >>> fake_path = (
    ...     '/path/to/sub-fakeSubject_ses-fakeSession_task-peer_run-3_'
    ...     'atlas-Schaefer400_space-MNI152NLin6_res-1x1x1_'
    ...     'desc-NilearnPearson_connectome.tsv')
    >>> strings_from_bids(fake_path)['desc']
    'NilearnPearson'
    >>> strings_from_bids(fake_path)['space']
    'MNI152NLin6'
    """
    from_bids = dict(
        tuple(entity.split('-', 1)) if '-' in entity else
        ('suffix', entity) for entity in final_func.split('/')[-1].split('_')
    )
    from_bids = {k: [from_bids[k]] for k in from_bids}
    if 'space' not in from_bids:
        from_bids['space'] = ['native']
    return from_bids


def generate_desc_qc(original_anat, final_anat, original_func,
                     final_func, n_vols_censored, space_T1w_bold,
                     movement_parameters, dvars,
                     framewise_displacement_jenkinson, dvars_after, fdj_after):
    # pylint: disable=too-many-arguments, too-many-locals, invalid-name
    """Function to generate an RBC-style QC CSV

    Parameters
    ----------
    original_anat : str
        path to original 'T1w' image

    final_anat : str
        path to 'desc-preproc_T1w' image

    original_func : str
        path to original 'bold' image

    final_bold : str
        path to 'desc-preproc_bold' image

    n_vols_censored : int

    space_T1w_bold : str
        path to 'space-T1w_desc-mean_bold' image

    movement_parameters: str
        path to movement parameters

    dvars : str
        path to DVARS before motion correction

    framewise_displacement_jenkinson : str
        path to framewise displacement (Jenkinson) before motion correction

    dvars_after : str
        path to DVARS on final 'bold' image

    fdj_after : str
        path to framewise displacement (Jenkinson) on final 'bold' image

    Returns
    -------
    str
        path to XCP QC TSV
    """
    columns = (
        'sub,ses,task,run,desc,space,meanFD,relMeansRMSMotion,'
        'relMaxRMSMotion,meanDVInit,meanDVFinal,nVolCensored,nVolsRemoved,'
        'motionDVCorrInit,motionDVCorrFinal,coregDice,coregJaccard,'
        'coregCrossCorr,coregCoverage,normDice,normJaccard,normCrossCorr,'
        'normCoverage'.split(',')
    )

    images = {
        'original_anat': nb.load(original_anat),
        'original_func': nb.load(original_func),
        'final_anat': nb.load(final_anat),
        'final_func': nb.load(final_func),
        'space-T1w_bold': nb.load(space_T1w_bold)
    }

    # `sub` through `space`
    from_bids = strings_from_bids(final_func)

    # `nVolCensored` & `nVolsRemoved`
    shape_params = {'nVolCensored': n_vols_censored,
                    'nVolsRemoved': images['final_func'].shape[3] -
                    images['original_func'].shape[3]}

    # `meanFD (Jenkinson)`
    if isinstance(final_func, BufferedReader):
        final_func = final_func.name
    qc_filepath = os.path.join(os.getcwd(), 'xcpqc.tsv')

    desc_span = re.search(r'_desc-.*_', final_func)
    if desc_span:
        desc_span = desc_span.span()
        final_func = '_'.join([
            final_func[:desc_span[0]],
            final_func[desc_span[1]:]
        ])
    del desc_span
    power_params = {'meanFD': np.mean(np.loadtxt(
        framewise_displacement_jenkinson))}

    # `relMeansRMSMotion` & `relMaxRMSMotion`
    mot = np.genfromtxt(movement_parameters).T
    # Relative RMS of translation
    rms = np.sqrt(mot[3] ** 2 + mot[4] ** 2 + mot[5] ** 2)
    rms_params = {
        'relMeansRMSMotion': [np.mean(rms)],
        'relMaxRMSMotion': [np.max(rms)]
    }

    # `meanDVInit` & `meanDVFinal`
    meanDV = {'meanDVInit': np.mean(np.loadtxt(dvars))}
    try:
        meanDV['motionDVCorrInit'] = dvcorr(
            dvars, framewise_displacement_jenkinson)
    except ValueError as value_error:
        meanDV['motionDVCorrInit'] = f'ValueError({str(value_error)})'
    if dvars_after:
        if not fdj_after:
            fdj_after = framewise_displacement_jenkinson
        meanDV['meanDVFinal'] = np.mean(np.loadtxt(dvars_after))
        try:
            meanDV['motionDVCorrFinal'] = dvcorr(dvars_after, fdj_after)
        except ValueError as value_error:
            meanDV['motionDVCorrFinal'] = f'ValueError({str(value_error)})'

    # Overlap
    overlap_images = {variable: image.get_fdata().ravel() for
                      variable, image in images.items() if
                      variable in ['space-T1w_bold', 'original_anat']}
    intersect = overlap_images['space-T1w_bold'] * overlap_images[
        'original_anat']
    vols = {variable: np.sum(image) for
            variable, image in overlap_images.items()}
    vol_intersect = np.sum(intersect)
    vol_sum = sum(vols.values())
    vol_union = vol_sum - vol_intersect
    overlap_params = {
        'coregDice': 2 * vol_intersect / vol_sum,
        'coregJaccard': vol_intersect / vol_union,
        'coregCrossCorr': np.corrcoef(
            overlap_images['space-T1w_bold'],
            overlap_images['original_anat'])[0, 1],
        'coregCoverage': vol_intersect / min(vols.values()),
        'normDice': 'N/A: native space',
        'normJaccard': 'N/A: native space',
        'normCrossCorr': 'N/A: native space',
        'normCoverage': 'N/A: native space'
    }

    qc_dict = {
        **from_bids,
        **power_params,
        **rms_params,
        **shape_params,
        **overlap_params,
        **meanDV
    }
    df = pd.DataFrame(qc_dict, columns=columns)
    df.to_csv(qc_filepath, sep='\t', index=False)
    return qc_filepath


def qc_xcp(wf, cfg, strat_pool, pipe_num, opt=None):
    # pylint: disable=unused-argument, invalid-name
    """
    {'name': 'qc_xcp',
     'config': ['pipeline_setup', 'output_directory', 'quality_control'],
     'switch': ['generate_xcpqc_files'],
     'option_key': 'None',
     'option_val': 'None',
     'inputs': ('bold', 'subject', 'scan', 'desc-preproc_bold',
                'desc-preproc_T1w', 'T1w',
                'space-T1w_desc-mean_bold', 'space-bold_desc-brain_mask',
                'movement-parameters', 'max-displacement', 'dvars',
                'framewise-displacement-jenkinson',
                ['rels-displacement', 'coordinate-transformation']),
     'outputs': ['xcpqc']}
    """
    original = {}
    final = {}
    original['anat'] = NodeData(strat_pool, 'T1w')
    original['func'] = NodeData(strat_pool, 'bold')
    final['anat'] = NodeData(strat_pool, 'desc-preproc_T1w')
    final['func'] = NodeData(strat_pool, 'desc-preproc_bold')
    t1w_bold = NodeData(strat_pool, 'space-T1w_desc-mean_bold')

    qc_file = pe.Node(Function(input_names=['original_func', 'final_func',
                                            'original_anat', 'final_anat',
                                            'space_T1w_bold',
                                            'movement_parameters',
                                            'n_vols_censored', 'dvars',
                                            'framewise_displacement_jenkinson',
                                            'dvars_after', 'fdj_after'],
                               output_names=['qc_file'],
                               function=generate_desc_qc,
                               as_module=True),
                      name=f'xcpqc_{pipe_num}')

    # motion "Final"
    motion_prov = strat_pool.get_cpac_provenance('movement-parameters')
    motion_correct_tool = check_prov_for_motion_tool(motion_prov)
    gen_motion_stats = motion_power_statistics('motion_stats-after_'
                                               f'{pipe_num}',
                                               motion_correct_tool)
    nodes = {
        node_data: NodeData(strat_pool, node_data) for node_data in [
            'subject', 'scan', 'space-bold_desc-brain_mask',
            'movement-parameters', 'max-displacement', 'dvars',
            'framewise-displacement-jenkinson'
        ]
    }
    if motion_correct_tool == '3dvolreg':
        nodes['coordinate-transformation'] = NodeData(strat_pool,
                                                      'coordinate-'
                                                      'transformation')
        wf.connect(nodes['coordinate-transformation'].node,
                   nodes['coordinate-transformation'].out,
                   gen_motion_stats, 'inputspec.transformations')
    elif motion_correct_tool == 'mcflirt':
        nodes['rels-displacement'] = NodeData(strat_pool, 'rels-displacement')
        wf.connect(nodes['rels-displacement'].node,
                   nodes['rels-displacement'].out,
                   gen_motion_stats, 'inputspec.rels_displacement')

    try:
        n_vols_censored = NodeData(strat_pool, 'n_vols_censored')
        wf.connect(n_vols_censored.node, n_vols_censored.out,
                   qc_file, 'n_vols_censored')
    except LookupError:
        qc_file.inputs.n_vols_censored = 'unknown'

    wf.connect([
        (original['anat'].node, qc_file, [
            (original['anat'].out, 'original_anat')]),
        (original['func'].node, qc_file, [
            (original['func'].out, 'original_func')]),
        (final['anat'].node, qc_file, [(final['anat'].out, 'final_anat')]),
        (final['func'].node, qc_file, [(final['func'].out, 'final_func')]),
        (t1w_bold.node, qc_file, [(t1w_bold.out, 'space_T1w_bold')]),
        (final['func'].node, gen_motion_stats, [
            (final['func'].out, 'inputspec.motion_correct')]),
        (nodes['subject'].node, gen_motion_stats, [
            (nodes['subject'].out, 'inputspec.subject_id')]),
        (nodes['scan'].node, gen_motion_stats, [
            (nodes['scan'].out, 'inputspec.scan_id')]),
        (nodes['movement-parameters'].node, gen_motion_stats, [
            (nodes['movement-parameters'].out,
             'inputspec.movement_parameters')]),
        (nodes['max-displacement'].node, gen_motion_stats, [
            (nodes['max-displacement'].out, 'inputspec.max_displacement')]),
        (nodes['space-bold_desc-brain_mask'].node, gen_motion_stats, [
            (nodes['space-bold_desc-brain_mask'].out, 'inputspec.mask')]),
        *[(nodes[node].node, qc_file, [
            (nodes[node].out, node.replace('-', '_'))
        ]) for node in ['movement-parameters', 'dvars',
                        'framewise-displacement-jenkinson']],
        (gen_motion_stats, qc_file, [('outputspec.DVARS_1D', 'dvars_after'),
                                     ('outputspec.FDJ_1D', 'fdj_after')])])

    outputs = {
        'xcpqc': (qc_file, 'qc_file'),
    }

    return (wf, outputs)
