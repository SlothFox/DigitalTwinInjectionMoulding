#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 13:25:16 2020

@author: alexander
"""

from sys import path
path.append(r"C:\Users\LocalAdmin\Documents\casadi-windows-py38-v3.5.5-64bit")

import os

import casadi as cs
import matplotlib.pyplot as plt
import numpy as np
import math
from DiscreteBoundedPSO import DiscreteBoundedPSO
import pandas as pd
import pickle as pkl

# Import sphere function as objective function
#from pyswarms.utils.functions.single_obj import sphere as f

# Import backend modules
# import pyswarms.backend as P
# from pyswarms.backend.topology import Star
# from pyswarms.discrete.binary import BinaryPSO

# Some more magic so that the notebook will reload external python modules;
# see http://stackoverflow.com/questions/1907993/autoreload-of-modules-in-ipython


from miscellaneous import *


# def SimulateModel(model,x,u,params=None):
#     # Casadi Function needs list of parameters as input
#     if params==None:
#         params = model.Parameters
    
#     params_new = []
        
#     for name in  model.Function.name_in():
#         try:
#             params_new.append(params[name])                      # Parameters are already in the right order as expected by Casadi Function
#         except:
#             continue
    
#     x_new = model.Function(x,u,*params_new)     
                          
#     return x_new

def ControlInput(ref_trajectories,opti_vars,k):
    """
    Übersetzt durch Maschinenparameter parametrierte
    Führungsgrößenverläufe in optimierbare control inputs
    """
    
    control = []
            
    for key in ref_trajectories.keys():
        control.append(ref_trajectories[key](opti_vars,k))
    
    control = cs.vcat(control)

    return control   
    
def CreateOptimVariables(opti, RefTrajectoryParams):
    """
    Defines all parameters, which parameterize reference trajectories, as
    opti variables and puts them in a large dictionary
    """
    
    # Create empty dictionary
    opti_vars = {}
    
    for param in RefTrajectoryParams.keys():
        
        dim0 = RefTrajectoryParams[param].shape[0]
        dim1 = RefTrajectoryParams[param].shape[1]
        
        opti_vars[param] = opti.variable(dim0,dim1)
    
    # Create one parameter dictionary for each phase
    # opti_vars['RefParamsInject'] = {}
    # opti_vars['RefParamsPress'] = {}
    # opti_vars['RefParamsCool'] = {}

    # for key in opti_vars.keys():
        
    #     param_dict = getattr(process_model,key)
        
    #     if param_dict is not None:
        
    #         for param in param_dict.keys():
                
    #             dim0 = param_dict[param].shape[0]
    #             dim1 = param_dict[param].shape[1]
                
    #             opti_vars[key][param] = opti.variable(dim0,dim1)
    #     else:
    #         opti_vars[key] = None
  
    return opti_vars

def MultiStageOptimization(process_model,ref):
    #Multi Stage Optimization for solving the optimal control problem
    
 
    # Create Instance of the Optimization Problem
    opti = cs.Opti()
    
    # Translate Maschinenparameter into opti.variables
    ref_params_opti = CreateOptimVariables(opti, 
                                           process_model.RefTrajectoryParams)
    
    # Number of time steps
    N = ref['data'].shape[0]
    
    # Create decision variables for states
    X = opti.variable(N,process_model.NumStates)
        
    # Initial Constraints
    opti.subject_to(X[0]==ref['data'][0])
    
    
    # System Dynamics as Path Constraints
    for k in range(N-1):
        
        if k<=ref['Umschaltpunkt']:
            U = ControlInput(process_model.RefTrajectoryInject,
                             ref_params_opti,k)
            
            # opti.subject_to(SimulateModel(process_model.ModelInject,X[k],U)==X[k+1])
            opti.subject_to(
                process_model.ModelInject.OneStepPrediction(X[k],U)==X[k+1])
            
        elif k>ref['Umschaltpunkt']:
            U = ControlInput(process_model.RefTrajectoryPress,
                             ref_params_opti,k)
            # opti.subject_to(SimulateModel(process_model.ModelPress,X[k],U)==X[k+1])
            
            opti.subject_to(
                process_model.ModelPress.OneStepPrediction(X[k],U)==X[k+1])            


        else:
             U=None # HIER MUSS EIN MODELL FÜR DIE ABKÜHLPHASE HIN
    
    ''' Further Path Constraints (to avoid values that might damage the machine or in 
    other ways harmful or unrealistic) '''
    
    # TO DO #
    
    
    # Final constraint
    opti.subject_to(X[-1]==ref['data'][-1])
    
    
    # Set initial values for Machine Parameters
    for key in ref_params_opti:
        opti.set_initial(ref_params_opti[key],process_model.RefTrajectoryParams[key])

    # Set initial values for state trajectory ??
    # for key in model.Maschinenparameter_opti:
    #     opti.set_initial(model.Maschinenparameter_opti[key],CurrentParams[key])      
    
    # Define Loss Function    
    opti.minimize(sumsqr(X-ref['data']))
    
    #Choose solver
    opti.solver('ipopt')
    
    # Get solution
    sol = opti.solve()
    
    # Extract real values from solution
    values = OptimValues_to_dict(ref_params_opti,sol)
    values['X'] = sol.value(X)

    
    return values

def SingleStageOptimization(model,ref,N):
    """ 
    single shooting procedure for optimal control of a scalar final value
    
    model: Quality Model
    ref: skalarer Referenzwert für Optimierungsproblem
    N: Anzahl an Zeitschritten
    """
    
    # Create Instance of the Optimization Problem
    opti = cs.Opti()
    
    # Create decision variables for states
    U = opti.variable(N,1)
        
    # Initial quality 
    x = 0
    y = 0
    X = [x]
    Y = [y]
    
    # Simulate Model
    for k in range(N):
        out = SimulateModel(model.ModelQuality,X[k],U[k],model.ModelParamsQuality)
        X.append(out[0])
        Y.append(out[1])
            
    X = hcat(X)
    Y = hcat(Y)
    
    # Define Loss Function  
    opti.minimize(sumsqr(Y[-1]-ref))
                  
    #Choose solver
    opti.solver('ipopt')
    
    # Get solution
    sol = opti.solve()   

    # Extract real values from solution
    values = {}
    values['U'] = sol.value(U)
    
    return values






