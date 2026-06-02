# HVAC

Deep reinforcement learning (DRL) project for co-optimizing HVAC energy consumption, thermal comfort, and indoor air quality.

This repository is based on the paper **“Deep reinforcement learning control for co-optimizing energy consumption, thermal comfort, and indoor air quality in an office building”**. The study proposes a DDPG-based controller for a central HVAC system and evaluates it against rule-based and MPC baselines.

## Overview

The project focuses on supervisory control of a central HVAC system in an office-type test cell.  
The control objective is to balance:

- energy consumption
- thermal comfort
- indoor CO2 concentration
- indoor PM2.5 concentration

A hybrid simulation environment is used to train and evaluate the DRL agent before deployment.

## Key ideas

- **Algorithm**: Deep Deterministic Policy Gradient (DDPG)
- **State space**: outdoor weather, outdoor air quality, and indoor zone conditions
- **Action space**: chilled water supply temperature setpoint, outdoor air damper opening, supply air fan speed, and air purifier ON/OFF
- **Simulation**: hybrid model combining HVAC dynamics, building envelope dynamics, humidity, CO2, and PM2.5 models
- **Baselines**: rule-based controller and MPC controller

## Repository structure

```text
checkpoints/   model checkpoints and saved training artifacts
data/          input data and/or simulation data
drl/           DRL agent implementation
simulator/     hybrid simulation environment
main.py        main entry point
train.py       training script
evaluate.py    evaluation script
```

## Research summary

The paper reports that the DRL controller can reduce energy use while maintaining comfort and indoor air quality constraints. It also compares the DRL method with a rule-based controller and an MPC controller to highlight practical trade-offs between performance and computational cost.

## How to run

The repository contains separate scripts for training and evaluation.

### Training
```bash
python train.py
```

### Evaluation
```bash
python evaluate.py
```

> Note: If your local environment requires specific command-line arguments or configuration files, adjust the commands according to the code in this repository.

## Expected workflow

1. Prepare the dataset and simulation inputs.
2. Train the DDPG agent in the hybrid simulator.
3. Save checkpoints during training.
4. Evaluate the trained policy on test scenarios.
5. Compare DRL results with the rule-based and MPC baselines.

## Reference paper

Fangzhou Guo, Sang woo Ham, Donghun Kim, Hyeun Jun Moon.  
*Deep reinforcement learning control for co-optimizing energy consumption, thermal comfort, and indoor air quality in an office building.*  
Applied Energy, 2025. DOI: 10.1016/j.apenergy.2024.124467

## License

Add a license file if you want to define how this repository can be used and redistributed.
