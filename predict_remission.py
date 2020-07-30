#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May 19 16:36:26 2020

@author: k1511004
"""

"""
Created on Tue Apr  7 11:56:16 2020

@author: k1511004
"""

# import what we need
import sys
from scipy.linalg import logm
import numpy as np
import pandas as pd
from sklearn.model_selection import ShuffleSplit, StratifiedShuffleSplit
from sklearn import svm
#from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, classification_report, r2_score, mean_squared_error, recall_score, balanced_accuracy_score
from sklearn.linear_model import LogisticRegression
from neuroCombat import neuroCombat
from neuroCombatCV3 import fit_transform_neuroCombat, apply_neuroCombat_model, ShuffleSplitFixed
from sklearn.preprocessing import OneHotEncoder
from riem_mglm import mglm_spd, logmap_spd
from sklearn.kernel_ridge import KernelRidge
from sklearn.metrics import mean_absolute_error, roc_auc_score, balanced_accuracy_score, accuracy_score
from scipy.stats import pearsonr
from datetime import datetime
from anatomical_covariance import cortical_regional_means, anatomical_covariance_matrix
from os import listdir
from neuroHarmonize import harmonizationLearn, harmonizationApply
from sklearn.cross_decomposition import PLSRegression, CCA
#import pyGPs_mod
#from pyGPs_mod import mean, cov, GPR

# function to calculate response to treatment at each timepoint
def response_to_treatment(x) :
    
    total_panss = x[0]
    baseline_panss = x[1]
    
    if np.isnan(baseline_panss) :
        
        return 'N/A'
    
    elif total_panss / baseline_panss < 0.8 :
        
        return 'response'
    
    else :
        
        return 'non-response'

# function to caculate AUCs for PANSS using the remission criteria
def PANSS_remission_AUC(pred_PANSS, remission) :
    
    # get intervals between all predicted panss
    pred_PANSS_flat = pred_PANSS.flatten()
    pred_PANSS_sorted = np.sort(pred_PANSS_flat)
    intervals = np.zeros((len(pred_PANSS_flat) + 1,))
    intervals[1:-1] = (pred_PANSS_sorted[1:] + pred_PANSS_sorted[:-1])/2
    
    # add end values to intervals, less than smallest PANSS scores and greater than largest
    intervals[0] = pred_PANSS_sorted[0] - 1
    intervals[-1] = pred_PANSS_sorted[-1] + 1

    # allocate memory to hold tpr, fpr
    tpr = np.zeros_like(intervals)
    fpr = np.zeros_like(intervals)
    
    # roll through intervals, calculating tpr & fpr for each interval value as threshold in remission rule
    print ('calculating AUC..')
    for i, threshold in enumerate(intervals) :
        
        threshold_remission = np.all(pred_PANSS <=threshold, axis=1).astype(int)
        tpr[i] = accuracy_score(remission[remission == 1], threshold_remission[remission == 1])
        fpr[i] = 1 - accuracy_score(remission[remission == 0], threshold_remission[remission == 0])
        
    AUC = np.trapz(fpr, tpr)
    return AUC
        
def results_summary(true_PANSS, pred_PANSS, n_PANSS_items, pred_remission, true_remission) :
    
    mae = 0
    r2 = 0
    std = 0
    for i in range(n_PANSS_items) :

        mae = mae + mean_absolute_error(pred_PANSS[:, i], true_PANSS[:, i])
        r2 = r2 + pearsonr(pred_PANSS[:, i], true_PANSS[:, i])[0]
        std = std + np.std(true_PANSS[:, i])
    
    mae = mae/n_PANSS_items
    r2 = r2 / n_PANSS_items
    std = std / n_PANSS_items
    
    bal_acc = balanced_accuracy_score(true_remission, pred_remission)
    roc_auc = PANSS_remission_AUC(pred_PANSS, true_remission)
    
    return mae, r2, std, bal_acc, roc_auc
    
    

# set directories 
#sMRI_data_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/Prelim_FEP_dataset/174_subjects_Oct_19/Data/sMRI/'
sMRI_data_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/Prelim_FEP_dataset/253_subjects_Apr_20/Data/sMRI/FS_data/'
fMRI_data_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/Prelim_FEP_dataset/253_subjects_Apr_20/Data/fMRI/'
FS_data_dir = sMRI_data_dir
metadata_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/Prelim_FEP_dataset/253_subjects_Apr_20/metadata/'
outcomes_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/FEP/metadata/'
results_dir = '/home/k1511004/Data/PSYSCAN/WP5_data/FEP/full_cohort_results/'

# set options
min_site_size = 5
max_mean_SP = 7.5

print('running!')

# do we want to exclude subjects where there is a problem with the T1 image?
T1W_motion_exclude_flag = True

# do we want to correct for site?
site_correction = 'comBat_supervised'

# what timepoint do we want to predict?
timepoint = 'Month_06'

# set data type
data_type = 'fMRI'

# excldue site 16?
exclude_site_16 = False

# inialise regressor and any relevant parameters
method = 'ridge'
n_components = 50
alpha= []

if method == 'ridge' :

    rgr = KernelRidge(kernel='precomputed')
    
elif method == 'PLS' :

    rgr = PLSRegression(n_components=n_components)
    
elif method == 'CCA' :

    rgr = CCA(n_components=n_components)
    
    

# anatomical covariance matrix parameters: atlas choice and number of histogram bins
atlas = 'Cambridge'
n_bins = 2
hemispheres = 'both'

# list of PANSS items used in Andreasen remission criteria
# see table 2 in 'Remission in Schizophrenia: Proposed Criteria and Rationale for Consensus' from Andreasen et al
remission_PANSS_items = ['panss_p1', 'panss_g9', 'panss_p3', 'panss_p2', 'panss_g5', 'panss_n1', 'panss_n4', 'panss_n6']
n_PANSS_items = len(remission_PANSS_items)

if data_type == 'fMRI' or data_type == 'sMRI_fMRI_subjects' :

    data_file = 'covariance_data_scaled_GraphLasso.npy'
    data = np.load(fMRI_data_dir + data_file)
    #
    # read in data subjects + motion metadata
    data_subjects = pd.read_excel(metadata_dir + 'FEP_fMRI_253subjs.xlsx')
    
    data = pd.DataFrame(data)
    data_subjects = pd.concat((data_subjects, data), axis=1)
    
    # filter out all data rows with all-zeros
    to_keep = (~(data_subjects.iloc[:, 9:]==0).all(axis=1)).tolist()
    data_subjects = data_subjects.iloc[to_keep, :]
    
    # read in extra metadata for age and sex
    # 1) subject data for sex and DOB
    # add Site column
    # then join on subject
    subject_metadata = pd.read_csv(metadata_dir + 'PSYSCAN_demographics.csv', delimiter='|')
    subject_metadata['Site'] = subject_metadata['Site'] = subject_metadata['Subject ID'].apply(lambda x: int(x[4:6]))
    names = data_subjects.columns.values
    names[0] = 'Subject ID'
    subject_metadata_data = pd.merge(subject_metadata, data_subjects, on='Subject ID', how='inner')
    
    # remove data with excessive motion in the fMRI or bad registration
    to_keep = (subject_metadata_data[['Co-reg?', 'fMRI ok?']]=='ok').all(axis=1).tolist()
    subject_metadata_data = subject_metadata_data.iloc[to_keep, :]
    
    # optionally exclude subjects wtih excessive motion on T1W scan
    if T1W_motion_exclude_flag :
    
        to_keep = (subject_metadata_data['T1w QC'] == 'ok').to_list()
        subject_metadata_data = subject_metadata_data.iloc[to_keep, :]
        
    # read in outcomes
    outcomes = pd.read_excel(outcomes_dir + 'Month_02_Month_06_outcomes.xlsx')
    outcomes.rename({'subjectid':'Subject ID'}, axis=1, inplace=True)
    
    # extract the columns we need
    timepoint_panss_cols = list(map(lambda x: timepoint + '|' + x, remission_PANSS_items))
    outcomes = outcomes[['Subject ID', 'Baseline|assessment age'] + timepoint_panss_cols]
    
    # filter out rows where baseline age or selected panss items are msising/nan
    outcomes = outcomes[outcomes[timepoint_panss_cols].notna().all(axis=1)]
    
    # add column for remission (at chosen timepoint): all relevant panss items <=3
    outcomes['remission'] = outcomes[timepoint_panss_cols].apply(lambda x: x<=3).all(axis=1)
    
    # join outcomes to metadata/data
    outcomes_metadata_data = pd.merge(outcomes, subject_metadata_data, on='Subject ID')
    
    # remove data from sites with < min_site_size subjects
    site_counts = outcomes_metadata_data['Site'].value_counts()
    to_keep_sites = pd.Series(site_counts[site_counts >= min_site_size].index)
    if exclude_site_16 :
        
        to_keep_sites = to_keep_sites[to_keep_sites.apply(lambda x: not x == 16)] 
    
    outcomes_metadata_data = outcomes_metadata_data[outcomes_metadata_data['Site'].isin(to_keep_sites)]
    
    # get sMRI data for matching subjects if needed
    if data_type == 'sMRI_fMRI_subjects' :
        
        sMRI_subjects = outcomes_metadata_data['Subject ID'].to_list()        
        n_subjects = len(sMRI_subjects)
        anatomical_covariance_matrix_1, lh_ROIs_1, rh_ROIs_1 = anatomical_covariance_matrix(FS_data_dir + sMRI_subjects[0], atlas, n_bins, 'thickness', hemispheres)
        n_regions = np.shape(anatomical_covariance_matrix_1)[0]
        n_covs = n_regions * n_regions
        tril_inds = np.ravel_multi_index(np.tril_indices(n_regions, k=-1), (n_regions, n_regions))
        anatomical_covariance_data = np.zeros((n_subjects, n_covs))
        anatomical_covariance_data[0, :] = np.reshape(anatomical_covariance_matrix_1, (1, n_covs))
    
        # roll through remaining subjects
        # check ROIs match as we go
        # initialise empty lists of subject with non-matching ROIs
        ROI_mismatch_subjects = []
        ROI_mismatch = False
        for i in range(1, n_subjects) :
    
            print (i)
    
            subj_anatomical_covariance_matrix, lh_ROIs, rh_ROIs = anatomical_covariance_matrix(FS_data_dir + sMRI_subjects[i], atlas, n_bins, 'thickness', hemispheres)
            if (not np.array_equal(lh_ROIs, lh_ROIs_1)) or (not np.array_equal(rh_ROIs, rh_ROIs_1)) :
        
                print ('ROI mismatch!')
                ROI_mismatch = True
                ROI_mismatch_subjects.append(sMRI_subjects[i])
        
                #    try again, this this imposing the ROI labels
                subj_anatomical_covariance_matrix, lh_ROIs, rh_ROIs = anatomical_covariance_matrix(sMRI_data_dir + sMRI_subjects[i], atlas, n_bins, 'thickness', hemispheres, lh_ROI_labels = lh_ROIs_1, rh_ROI_labels = rh_ROIs_1)

            else :
        
                anatomical_covariance_data[i, :] = np.reshape(subj_anatomical_covariance_matrix, (1, n_covs))    
        
        # replace fMRI data in outcomes_metadata_data
        outcomes_metadata_data = outcomes_metadata_data.iloc[:, :10]
        outcomes_metadata_data = outcomes_metadata_data.reset_index(drop=True)
        outcomes_metadata_data = pd.concat([outcomes_metadata_data, pd.DataFrame(anatomical_covariance_data)], axis=1)
        foo =1
        
    # pull out data, metadata and outcomes again
    data = outcomes_metadata_data.iloc[:, 22:].as_matrix()
    metadata = outcomes_metadata_data.iloc[:, :22]
    site = metadata['Site'].values
        
elif data_type == 'sMRI' :
    
    # get the list of available subjects with sMRI
    available_subjects = listdir(FS_data_dir)
    
    if T1W_motion_exclude_flag :
    
        # exclude subjects with motion artifacts
        exclude = pd.read_csv(sMRI_data_dir + 'exclude_sMRI.txt', header=None)[0].tolist()
        available_subjects = list(filter(lambda x: not x in exclude, available_subjects))
        available_subjects = pd.DataFrame({'Subject ID':available_subjects})
        
    # read in extra metadata for age and sex
    # 1) subject data for sex and DOB
    # then join on subject
    subject_metadata = pd.read_csv(metadata_dir + 'PSYSCAN_demographics.csv', delimiter='|')
    subject_metadata = pd.merge(available_subjects, subject_metadata, on='Subject ID', how='inner')
        
    # read in outcomes
    outcomes = pd.read_excel(outcomes_dir + 'Month_02_Month_06_outcomes.xlsx')
    outcomes.rename({'subjectid':'Subject ID'}, axis=1, inplace=True)
    
    # filter out rows where panss fpr baseline or prediction timepoint is missing/nan
    timepoint_panss_cols = list(filter(lambda x: timepoint + '|panss' in x, outcomes.columns))
    baseline_panss_cols = list(filter(lambda x: 'Baseline|panss' in x, outcomes.columns))
    outcomes = outcomes[outcomes[timepoint_panss_cols].notna().any(axis=1)]
    outcomes = outcomes[outcomes[baseline_panss_cols].notna().any(axis=1)]
    
    # extract the columns we need
    outcomes = outcomes[['Subject ID', 'Baseline|assessment age', 'Baseline|total_panss', timepoint + '|total_panss', timepoint + '|response_to_treatment']]
    
    # join outcomes to metadata/data
    outcomes_metadata = pd.merge(outcomes, subject_metadata, on='Subject ID')
    outcomes_metadata['Site'] = outcomes_metadata['Subject ID'].apply(lambda x: int(x[4:6]))
    
    # remove data from sites with < min_site_size subjects
    site_counts = outcomes_metadata['Site'].value_counts()
    to_keep_sites = pd.Series(site_counts[site_counts >= min_site_size].index)
    if exclude_site_16 :
        
        to_keep_sites = to_keep_sites[to_keep_sites.apply(lambda x: not x == 16)]
    outcomes_metadata = outcomes_metadata[outcomes_metadata['Site'].isin(to_keep_sites)]
    
    # use list of avaailable subjects to generate sMRI data
    sMRI_subjects = outcomes_metadata['Subject ID'].to_list()        
    n_subjects = len(sMRI_subjects)
    anatomical_covariance_matrix_1, lh_ROIs_1, rh_ROIs_1 = anatomical_covariance_matrix(FS_data_dir + sMRI_subjects[0], atlas, n_bins, 'thickness', hemispheres)
    n_regions = np.shape(anatomical_covariance_matrix_1)[0]
    n_covs = n_regions * n_regions
    tril_inds = np.ravel_multi_index(np.tril_indices(n_regions, k=-1), (n_regions, n_regions))
    anatomical_covariance_data = np.zeros((n_subjects, n_covs))
    anatomical_covariance_data[0, :] = np.reshape(anatomical_covariance_matrix_1, (1, n_covs))
    
    # roll through remaining subjects
    # check ROIs match as we go
    # initialise empty lists of subject with non-matching ROIs
    ROI_mismatch_subjects = []
    ROI_mismatch = False
    for i in range(1, n_subjects) :

        print (i)

        subj_anatomical_covariance_matrix, lh_ROIs, rh_ROIs = anatomical_covariance_matrix(FS_data_dir + sMRI_subjects[i], atlas, n_bins, 'thickness', hemispheres)
        if (not np.array_equal(lh_ROIs, lh_ROIs_1)) or (not np.array_equal(rh_ROIs, rh_ROIs_1)) :
    
            print ('ROI mismatch!')
            ROI_mismatch = True
            ROI_mismatch_subjects.append(sMRI_subjects[i])
    
            #    try again, this this imposing the ROI labels
            subj_anatomical_covariance_matrix, lh_ROIs, rh_ROIs = anatomical_covariance_matrix(sMRI_data_dir + sMRI_subjects[i], atlas, n_bins, 'thickness', hemispheres, lh_ROI_labels = lh_ROIs_1, rh_ROI_labels = rh_ROIs_1)

        else :
    
            anatomical_covariance_data[i, :] = np.reshape(subj_anatomical_covariance_matrix, (1, n_covs))
        
        
    foo=1
    
    # rename for compatibility
    data = anatomical_covariance_data
    metadata = outcomes_metadata
    site = metadata['Site'].values

n_subjects, n_connections = np.shape(data)
n_regions = int(np.sqrt(n_connections))
tril_inds = np.ravel_multi_index(np.tril_indices(n_regions, k=-1), (n_regions, n_regions))
n_connectivities = len(tril_inds)
logm_connectivity_data = np.zeros((n_subjects, n_connectivities))

# do site correction
if data_type == 'fMRI' and (site_correction == 'comBat_unsupervised' or site_correction == 'comBat_supervised' or site_correction == 'None') :

    # take matrix logs at start
    for i in range(n_subjects) :
    
        print(i)
    
        connectivity_vector = data[i, :]
        connectivity_matrix = np.reshape(connectivity_vector, (n_regions, n_regions))
        logm_connectivity_matrix = logm(connectivity_matrix)
        logm_connectivity_vector = np.reshape(logm_connectivity_matrix, (n_regions * n_regions, ))
        logm_connectivity_data[i, :] = logm_connectivity_vector[tril_inds]
        
if data_type == 'sMRI' or data_type == 'sMRI_fMRI_subjects' :
    
    logm_connectivity_data = data[:, tril_inds]

# do unsupervised comBat correction if that is selected
if site_correction == 'comBat_unsupervised' : 
       
    logm_connectivity_data = neuroCombat(logm_connectivity_data, metadata, batch_col = 'Site')
    
# do MGLM correction if that is selected
if site_correction == 'MGLM' : 
        
    # pull out site variable and convert to one-hot
    enc = OneHotEncoder(sparse=False)
    enc.fit(site.reshape(-1,1))
    site_one_hot = enc.transform(site.reshape(-1, 1))
    site_one_hot = np.transpose(site_one_hot)

    # transpose and reshape the connectivity data
    data_perm = np.reshape(data, (n_subjects, n_regions, n_regions))
    data_perm = np.transpose(data_perm, (1, 2, 0))
    
    # generate MGLM regressed data
    p, V, E, Y_hat, gnorm = mglm_spd(site_one_hot, data_perm, 100)
    
    # calculate matrix 'residuals'
    for i in range(n_subjects) :
        
        mglm_corrected_matrix = Y_hat[:, :, i]
        mglm_residuals_matrix = logmap_spd(mglm_corrected_matrix, data_perm[:, :, i])
        mglm_residuals_vector = np.reshape(mglm_residuals_matrix, (n_regions * n_regions, ))
        logm_connectivity_data[i, :] = mglm_residuals_vector[tril_inds]

# set up MCCV
n_repeats = 200
test_fraction = 0.2
train_inds_all, test_inds_all, test_size = ShuffleSplitFixed(logm_connectivity_data, site, site, test_fraction, n_repeats)
train_size = n_subjects - test_size
#ss = StratifiedShuffleSplit(n_splits = n_repeats, test_size = test_size,    )

# pull out targets (followup remssion PANSS) and subject ids plus ground truth remission
remission_PANSS = metadata[timepoint_panss_cols].values
subjectids = metadata['Subject ID'].to_list()
remission = metadata['remission'].values.astype(int)

# data structures to hold results
predicted_remission_PANSS = np.zeros((n_repeats * test_size, n_PANSS_items))
test_remission_PANSS = np.zeros_like(predicted_remission_PANSS)
test_remission = np.zeros((n_repeats * test_size, 1))
pred_remission = np.zeros((n_repeats * test_size, 1))

# initialise list of test subjects
test_subjects = []

# precompute kernel matrix
K = np.dot(logm_connectivity_data, np.transpose(logm_connectivity_data))

# do MCCV
for i in range(n_repeats) :
    
    train_index = train_inds_all[i]
    test_index = test_inds_all[i]

    print (i)    
    
    # calculate output indices
    start_ind = i * test_size
    stop_ind = start_ind + test_size
    
    train_targets = remission_PANSS[train_index, :]
    test_targets = remission_PANSS[test_index, :]
    test_subjects = test_subjects + list(np.array(subjectids)[test_index])
             
    train_data = logm_connectivity_data[train_index, :]
    test_data = logm_connectivity_data[test_index, :]
    
    
    
    # do supervised site correction?
    if site_correction == 'comBat_supervised' :
    
        # correct training data
        train_data, model = fit_transform_neuroCombat(train_data, metadata.iloc[train_index, :], 'Site', continuous_cols=timepoint_panss_cols)
        
        # correct testing dara
        test_data = apply_neuroCombat_model(test_data,
                      metadata.iloc[test_index, :], model,
                      'Site')
        
        train_K = np.dot(train_data, np.transpose(train_data))
        cross_K = np.dot(test_data, np.transpose(train_data))
        
    else :
        
        train_K  = K[train_index, :][:, train_index]
        cross_K = K[test_index, :][:, train_index]
    
    if method == 'ridge' :
    
        # train rge for followup PANSS and predict
        for j in range(n_PANSS_items) :
            
            rgr.fit(train_K, train_targets[:, j])
            preds = rgr.predict(cross_K) 
        
            # store results
            predicted_remission_PANSS[start_ind:stop_ind, j] = preds
            test_remission_PANSS[start_ind:stop_ind, j] = remission_PANSS[test_index, j]
            
    if method == 'PLS' or method == 'CCA' or method == 'multitask' :
        
        rgr.fit(train_data, train_targets)
        preds = rgr.predict(test_data)
        
        # store results
        predicted_remission_PANSS[start_ind:stop_ind, :] = preds
        test_remission_PANSS[start_ind:stop_ind, :] = remission_PANSS[test_index, :]
        
    test_remission[start_ind:stop_ind, 0] = remission[test_index]
    pred_remission[start_ind:stop_ind, 0] = np.all(predicted_remission_PANSS[start_ind:stop_ind, :] <=3, axis=1).astype(int)


# put results in a DF with subjects
test_subjects = list(map(lambda x: str(x), test_subjects))
subjects_remission_results = pd.DataFrame(test_subjects)
subjects_remission_results['Site'] = subjects_remission_results[0].apply(lambda x: int(x[4:6]))
test_PANSS_cols = list(map(lambda x: 'test ' + x, timepoint_panss_cols))
pred_PANSS_cols = list(map(lambda x: 'pred ' + x, timepoint_panss_cols))
subjects_remission_results[test_PANSS_cols] = pd.DataFrame(test_remission_PANSS)
subjects_remission_results['remission'] = pd.Series(np.squeeze(test_remission))
subjects_remission_results[pred_PANSS_cols] = pd.DataFrame(predicted_remission_PANSS)
subjects_remission_results['predicted remission'] = pd.Series(np.squeeze(pred_remission))
pred_PANSS = subjects_remission_results[pred_PANSS_cols].values
true_PANSS = subjects_remission_results[test_PANSS_cols].values

#
## open file for storing results
#date_string = datetime.now().strftime("%d-%m-%Y_%I-%M-%S_%p")
#results_file = open(results_dir + 'predict_treatment_response_results_' + data_type + '_'+ date_string + '.txt', "w") 
#
## accuracy of predicted response/nonresponse
pred_remission = subjects_remission_results['predicted remission'].values
true_remission = subjects_remission_results['remission'].values

mae, r2, std, bal_acc, roc_auc = results_summary(true_PANSS, pred_PANSS, n_PANSS_items, pred_remission, true_remission)

print ('Overall results:')
print ('Total PANSS prediction - mae = ' + str(mae) + ' (std) = ' + str(std))
print ('Total PANSS prediction - correlation = ' + str(r2))
print ('Response/non-response prediction - balanced accuracy = ' + str(bal_acc))
print ('Response/non-response prediction - AUC = ' + str(roc_auc))
#results_file.write(str(mae) + '_(' + str(std) + ')\n')
#results_file.write(str(r2[0]) + '\n')
#results_file.write(str(bal_acc) + '\n')
#results_file.write(str(roc_auc) + '\n')
#
## look at site breakdowns
unique_sites = list(set(site))
#
print ('Results by site:')
for site in unique_sites:
    
    print ('Site ' + str(site) + ' results:')
    site_results = subjects_remission_results[subjects_remission_results['Site'] == site]
    pred_PANSS = site_results[pred_PANSS_cols].values
    true_PANSS = site_results[test_PANSS_cols].values
    pred_remission = site_results['predicted remission'].values
    true_remission = site_results['remission'].values
    mae, r2, std, bal_acc, roc_auc = results_summary(true_PANSS, pred_PANSS, n_PANSS_items, pred_remission, true_remission)
#    mae = mean_absolute_error(pred_PANSS, true_PANSS)
#    r2 = pearsonr(pred_PANSS, true_PANSS)
#    std = np.std(true_PANSS)
#    pred_response = site_results['predicted response to treatment'].values
#    true_response = site_results['response to treatment'].values
#    bal_acc = balanced_accuracy_score(true_response, pred_response)
#    try :
#    
#        roc_auc = roc_auc_score(true_response, PANSS_followup_ratio)
#        
#    except ValueError :
#        
#        roc_auc = 'No_AUC_as_only_one_class_is_present_for_this_site'
    
    print ('Total PANSS prediction - mae = ' + str(mae) + ' (std) = ' + str(std))
    print ('Total PANSS prediction - correlation = ' + str(r2))
    print ('Response/non-response prediction - balanced accuracy = ' + str(bal_acc))
    print ('Response/non-response prediction - AUC = ' + str(roc_auc))
#    results_file.write(str(mae) + '_(' + str(std) + ')\n')
#    results_file.write(str(r2[0]) + '\n')
#    results_file.write(str(bal_acc) + '\n')
#    results_file.write(str(roc_auc) + '\n')
#    
## close the results file
#results_file.close()    
