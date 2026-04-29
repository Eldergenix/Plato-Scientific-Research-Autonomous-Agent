We have data from recent binary black merger GW231123 detected in gravitational waves. 
The data is located in the two files: 
- ...../examples/GW231123/data/GW231123_NRSur7dq4.csv
- ...../examples/GW231123/data/GW231123_IMRPhenomXO4a.csv

These files contain samples from the posterior distribution corresponding to two different gravitational-wave waveform models which are detailed below. The meaning of each column can be found in the file header, but is also provided below for reference.

We are interested in understanding which ways the different models agree or differ in their prediction for GW231123. There are complex degeneracies in the high-dimensional posterior space which make this problem challenging. Analyze the datasets in detail and tell us what you have learned from it. Mention also any interesting astrophysical insights that you learn from this analysis, and what can be robustly concluded about statistical properties of the high-mass black hole merger GW231123. Make sure there is no repetition in plots in the paper.

For reference, the event was reported in https://arxiv.org/pdf/2507.08219

Below is a description of the models used for the two files mentioned above: 
- NRSur7dq4 is a time-domain waveform model that has been directly calibrated using Numerical Relativity simulations of binary black hole mergers. This model is particularly well-suited for events with short gravitational wave signals, such as GW231123, as it is designed to accurately capture the dynamics of the late inspiral, merger, and ringdown phases.
- IMRPhenomXO4a, on the other hand, is a phenomenological model that operates in the frequency domain. It combines post-Newtonian (PN) approximations during the inspiral phase with a numerical relativity calibration near the merger. This model provides a more global approximation of binary black hole waveforms and is specifically tailored for events that can be characterized over a wider range of frequencies.

Here is a description of the columns in the csv file:
'mass_1_source': Mass of the primary black hole
'mass_2_source': Mass of the secondary black hole
'a_1': Spin magnitude of the primary black hole
'a_2': Spin magnitude of the secondary black hole
'final_mass_source': Final mass the remnant black hole
'final_spin': Final spin of the remnant black hole
'redshift': Redshift of the event
'cos_tilt_1': Cosine of the spin tilt-angle of the primary black hole
'cos_tilt_2': Cosine of the spin tilt-angle of the secondary black hole
'chi_eff': Effective sum of spins components aligned with the orbital angular momentum
'chi_p': Effective spin parameter related to spin-orbit precession of the binary
'cos_theta_jn': Cosine of the inclination angle of the binary to the observer
'phi_jl': Azimuthal angle between the total and orbital angular momentum (called spin azimuth)
'log_likelihood': Log-likelihood of the samples

Use state-of-the-art methods to analyze the data. For every step, make plots and save the data you generate, as it may be used for other steps. When writing the code, write some lines to indicate whether the execution was successful or not. Join plots that are similar. Do not create dummy data. Do not include more than 10 figures in the paper. You have access to 8 cpus; for computationally heavy tasks, try to use all of them.