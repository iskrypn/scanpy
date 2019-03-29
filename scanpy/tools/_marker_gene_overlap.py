"""Calculate overlaps of rank_genes_groups marker genes with marker gene dictionaries
"""
import numpy as np
import pandas as pd

from typing import Union, Optional
from anndata import AnnData

from .. import logging as logg

def _calc_overlap_count(
    markers1: dict,
    markers2: dict,
):
    """Calculate overlap count between the values of two dictionaries

    Note: dict values must be sets
    """
    overlaps=np.zeros((len(markers1), len(markers2)))

    j=0
    for marker_group in markers1:
        tmp = [len(markers2[i].intersection(markers1[marker_group])) for i in markers2.keys()]
        overlaps[j,:] = tmp
        j += 1

    return overlaps


def _calc_overlap_coef(
    markers1: dict,
    markers2: dict,
):
    """Calculate overlap coefficient between the values of two dictionaries

    Note: dict values must be sets
    """
    overlap_coef=np.zeros((len(markers1), len(markers2)))

    j=0
    for marker_group in markers1:
        tmp = [len(markers2[i].intersection(markers1[marker_group]))/
               max(min(len(markers2[i]), len(markers1[marker_group])),1) for i in markers2.keys()]
        overlap_coef[j,:] = tmp
        j += 1

    return overlap_coef


def _calc_jaccard(
    markers1: dict,
    markers2: dict,
):
    """Calculate jaccard index between the values of two dictionaries

    Note: dict values must be sets
    """
    jacc_results=np.zeros((len(markers1), len(markers2)))

    j=0
    for marker_group in markers1:
        tmp = [len(markers2[i].intersection(markers1[marker_group]))/
               len(markers2[i].union(markers1[marker_group])) for i in markers2.keys()]
        jacc_results[j,:] = tmp
        j += 1

    return jacc_results


def marker_gene_overlap(
    adata: AnnData,
    reference_markers: dict,
    *,
    key: str = 'rank_genes_groups',
    method: Optional[str] = 'overlap_count',
    normalize: Union[str, None] = None,
    top_n_markers: Optional[int] = None,
    adj_pval_threshold: Optional[float] = None,
    key_added: Optional[str] = 'marker_gene_overlap'
):
    """Calculate an overlap score between data-deriven marker genes and provided markers

    Marker gene overlap scores can be quoted as overlap counts, overlap coefficients, or
    jaccard indices. The method returns a pandas dataframe which can be used to annotate
    clusters based on marker gene overlaps.

    This function was written by Malte Luecken.

    Parameters
    ----------
    adata
        The annotated data matrix.
    reference_markers
        A marker gene dictionary object. Keys should be strings with the cell identity name
        and values are sets of strings which match format of `adata.var_name`.
    key
        The key in `adata.uns` where the rank_genes_groups output is stored. This field
        should contain a dictionary with a `numpy.recarray()` under the key 'names'.
    method : `{'overlap_count', 'overlap_coef', 'jaccard'}`, optional (default: `overlap_count`)

    normalize : `{'reference', 'data', 'None'}`, optional (default: `None`)

    top_n_markers
       This is prioritized over `adj_pval_threshold`
    adj_pval_threshold

    key_added


    Returns
    -------
    Updates `adata.uns` with an additional field specified by the `key_added`
    parameter (default = 'marker_gene_overlap'). 

    Examples
    --------
    >>> adata = sc.datasets.pbmc68k_reduced()
    >>> 
    >>> 
    >>> 
    >>> 
    """
    # Test user inputs
    if key not in adata.uns:
        raise ValueError()

    avail_methods = {'overlap_count', 'overlap_coef', 'jaccard', 'enrich'}
    if method not in avail_methods:
        raise ValueError('Method must be one of {}.'.format(avail_methods))
    
    if normalize == 'None':
        normalize = None

    avail_norm = {'reference', 'data', None}
    if normalize not in avail_norm:
        raise ValueError('Normalize must be one of {}.'.format(avail_norm))
    
    if normalize is not None and method != 'overlap_count':
        raise ValueError('Can only normalize with method=`overlap_count`.')

    if not np.all([isinstance(val, set) for val in reference_markers.values()]):
        raise ValueError('Please ensure that `reference_markers` contains sets '
                         'of markers as values.')

    if adj_pval_threshold is not None:
        if adj_pval_threshold < 0:
            logg.warn('`adj_pval_threshold` was set below 0. '
                      'Threshold will be set to 0.')
            adj_pval_threshold = 0

        if adj_pval_threshold > 1:
            logg.warn('`adj_pval_threshold` was set above 1. '
                      'Threshold will be set to 1.')
            adj_pval_threshold = 1

        if top_n_markers is not None:
            logg.warn('Both `adj_pval_threshold` and `top_n_markers` is set. '
                      '`adj_pval_threshold` will be ignored.')
            
    if top_n_markers is not None:
        if top_n_markers < 1:
            logg.warn('`top_n_markers` was set below 1. '
                      '`top_n_markers` will be set to 1.')
            top_n_markers = 1
            

    # Get data-derived marker genes in a dictionary of sets
    data_markers = dict()
    cluster_ids = adata.uns[key]['names'].dtype.names

    for group in cluster_ids:

        if top_n_markers is not None:
            n_genes = min(top_n_markers, adata.uns[key]['names'].shape[0])
            data_markers[group] = set(adata.uns[key]['names'][group][:n_genes])

        elif adj_pval_threshold is not None:
            n_genes = (adata.uns[key]['pvals_adj'][group] < adj_pval_threshold).sum()
            data_markers[group] = set(adata.uns[key]['names'][group][:n_genes])
        else:
            data_markers[group] = set(adata.uns[key]['names'][group])

    # To do:
    # - allow to only use the top X marker genes calculated
    # - allow using a p-value cutoff for the genes
    # - test behaviour when 0 genes are selected by thresholds

    # Find overlaps
    if method == 'overlap_count':
        marker_match = _calc_overlap_count(reference_markers, data_markers)

        if normalize == 'reference':
            # Ensure rows sum to 1
            marker_match = marker_match/marker_match.sum(1)[:,np.newaxis]
            marker_match = np.nan_to_num(marker_match)

        elif normalize == 'data':
            #Ensure columns sum to 1
            marker_match = marker_match/marker_match.sum(0)
            marker_match = np.nan_to_num(marker_match)
            
    elif method == 'overlap_coef':
        marker_match = _calc_overlap_coef(reference_markers, data_markers)

    elif method == 'jaccard':
        marker_match = _calc_jaccard(reference_markers, data_markers)
        
    #Note:
    # Could add an 'enrich' option here (fisher's exact test or hypergeometric test),
    # but that would require knowledge of the size of the space from which the reference
    # marker gene set was taken. This is at best approximately known.
        
    # Create a pandas dataframe with the results
    marker_groups = list(reference_markers.keys())
    clusters = list(cluster_ids)
    marker_matching_df = pd.DataFrame(marker_match, index=marker_groups, columns=clusters)

    # Store the results
    adata.uns[key_added] = marker_matching_df

    logg.hint('added\n'
              '    \'{}\', marker overlap scores (adata.uns)'.format(key_added))

    return None
