#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 13:25:16 2020

@author: alexander
"""

from sys import path
path.append(r"C:\Users\LocalAdmin\Documents\casadi-windows-py38-v3.5.5-64bit")

import casadi as cs
import matplotlib.pyplot as plt
import numpy as np
from DiscreteBoundedPSO import DiscreteBoundedPSO
import pandas as pd

# Import sphere function as objective function
#from pyswarms.utils.functions.single_obj import sphere as f

# Import backend modules
# import pyswarms.backend as P
# from pyswarms.backend.topology import Star
# from pyswarms.discrete.binary import BinaryPSO

# Some more magic so that the notebook will reload external python modules;
# see http://stackoverflow.com/questions/1907993/autoreload-of-modules-in-ipython


from miscellaneous import *


def SimulateModel(model,x,u,params=None):
    # Casadi Function needs list of parameters as input
    if params==None:
        params = model.Parameters
    
    params_new = []
        
    for name in  model.Function.name_in():
        try:
            params_new.append(params[name])                      # Parameters are already in the right order as expected by Casadi Function
        except:
            continue
    
    x_new = model.Function(x,u,*params_new)     
                          
    return x_new
   
    
def CreateOptimVariables(opti, param_dict):
    
    Parameter = {}

    for key in param_dict.keys():
        
        dim0 = param_dict[key].shape[0]
        dim1 = param_dict[key].shape[1]
        
        Parameter[key] = opti.variable(dim0,dim1)

    opti_vars = Parameter
    
    return opti_vars

def MultiStageOptimization(model,ref):
    #Multi Stage Optimization for solving the optimal control problem
    
 
    # Create Instance of the Optimization Problem
    opti = cs.Opti()
    
    # Translate Maschinenparameter into opti.variables
    Fuehrungsparameter_opti = CreateOptimVariables(opti, model.Parameters)
    
    # Number of time steps
    N = ref['data'].shape[0]
    
    # Create decision variables for states
    NumStates = model.ModelInject.dim_x
    X = opti.variable(N,NumStates)
        
    # Initial Constraints
    opti.subject_to(X[0]==ref['data'][0])
    
    
    # System Dynamics as Path Constraints
    for k in range(N-1):
        
        if k<=ref['Umschaltpunkt']:
            U = model.ControlInput(Fuehrungsparameter_opti,k)
            opti.subject_to(SimulateModel(model.ModelInject,X[k],U)==X[k+1])

        elif k>ref['Umschaltpunkt']:
            U = model.ControlInput(Fuehrungsparameter_opti,k)
            opti.subject_to(SimulateModel(model.ModelPress,X[k],U)==X[k+1])

        else:
             U=None # HIER MUSS EIN MODELL FÜR DIE ABKÜHLPHASE HIN
    
    ''' Further Path Constraints (to avoid values that might damage the machine or in 
    other ways harmful or unrealistic) '''
    
    # TO DO #
    
    
    # Final constraint
    opti.subject_to(X[-1]==ref['data'][-1])
    
    
    # Set initial values for Machine Parameters
    for key in Fuehrungsparameter_opti:
        opti.set_initial(Fuehrungsparameter_opti[key],model.Fuehrungsparameter[key])

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
    values = OptimValues_to_dict(Fuehrungsparameter_opti,sol)
    values['X'] = sol.value(X)

    
    return values



def ModelTraining(model,data,initializations = 20, BFR=False, p_opts=None, s_opts=None):
    
    # Split in Training and Validation data
    
    results = [] 
    
    for i in range(0,initializations):
        
        # in first run use initial model parameters (useful for online training) 
        if i > 0:
            model.Initialize()
        
        # Estimate Parameters on training data
        new_params = ModelParameterEstimation(model,data)
        
        # Assign new parameters to model
        model.Parameters = new_params
        
        # Evaluate on Validation data
        u_val = data['u_val']
        x_ref_val = data['x_val']
        init_state_val = data['init_state_val']

        # Loop over all experiments
        
        e = 0
        
        for j in range(0,u_val.shape[0]):   
               
            # Simulate Model
            x = model.Simulation(init_state_val[j],u_val[j])
            x = np.array(x)
                     
            e = e + cs.sumsqr(x_ref_val[j] - x) 
        
        # Calculate mean error over all validation batches
        e = e / u_val.shape[0]
        e = np.array(e).reshape((1,))
        
        # save parameters and performance in list
        results.append([e,new_params])
    
    results = pd.DataFrame(data = results, columns = ['loss','params'])
    
    return results 

def HyperParameterPSO(model,data,param_bounds,n_particles,options,**kwargs):
    
    
    # Formulate Particle Swarm Optimization Problem
    dimensions_discrete = len(param_bounds.keys())
    lb = []
    ub = []
    
    for param in param_bounds.keys():
        
        lb.append(param_bounds[param][0])
        ub.append(param_bounds[param][1])
    
    bounds= (lb,ub)
    
    PSO_problem = DiscreteBoundedPSO(n_particles, dimensions_discrete, 
                                     options, bounds)
    
    cost_func_kwargs = {'model': model,
                        'param_bounds': param_bounds,
                        'n_particles': n_particles,
                        'dimensions_discrete': dimensions_discrete,
                        'training_history': 'path/file.pkl'}
    
    
    # Create Cost function
    def PSO_cost_function(swarm_position,**kwargs):
        
        # Load training history to avoid calculating stuff muliple times
       
        # Initialize empty array for costs
        cost = np.zeros((n_particles,1))
    
        for particle in range(0,n_particles):
         
            # Adjust model parameters according to particle
            for p in range(0,dimensions_discrete):  
                setattr(model,list(param_bounds.keys())[p],
                        swarm_position[particle,p])
            
            model.Initialize()
            
            # Estimate parameters
            results = ModelTraining(model,data,initializations = 2, 
                                    BFR=False, p_opts=None, s_opts=None)
            
            # calculate mean performance
            cost[particle] = results.loss.mean()
            cost = cost.reshape((n_particles,))
        return cost
    
    PSO_problem.optimize(PSO_cost_function, iters=100)
    
    return PSO_problem

def ModelParameterEstimation(model,data,p_opts=None,s_opts=None):
    """
    
    """
    
    
    u = data['u_train']
    x_ref = data['x_train']
    init_state = data['init_state_train']
    
    # Create Instance of the Optimization Problem
    opti = cs.Opti()
    
    params_opti = CreateOptimVariables(opti, model.Parameters)
    
    e = 0
    
    # Loop over all experiments
    for i in range(0,u.shape[0]):   
           
        # Simulate Model
        x = model.Simulation(init_state[i],u[i],params_opti)
        
        e = e + sumsqr(x_ref[i,:,:] - x)
    
    opti.minimize(e)
    
    # Solver options
    if p_opts is None:
        p_opts = {"expand":False}
    if s_opts is None:
        s_opts = {"max_iter": 10, "print_level":0}
    
    # Create Solver
    opti.solver("ipopt",p_opts, s_opts)
    
    
    # Set initial values of Opti Variables as current Model Parameters
    for key in params_opti:
        opti.set_initial(params_opti[key], model.Parameters[key])
    
    
    # Solve NLP, if solver does not converge, use last solution from opti.debug
    try: 
        sol = opti.solve()
    except:
        sol = opti.debug
        
    values = OptimValues_to_dict(params_opti,sol)
    
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






