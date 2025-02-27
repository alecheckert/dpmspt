#!/usr/bin/env python
"""
plot.py

"""
import sys
import os
import numpy as np 
import pandas as pd 
import matplotlib.pyplot as plt 
import seaborn as sns 
from scipy.ndimage import gaussian_filter

# Compute the likelihood of a set of diffusion coefficients,
# given a set of trajectories
from .lik import (
    likelihood_matrix,
    likelihood_matrix_fbm
)

# Calculate trajectory length
from .utils import track_length, load_tracks

# Defocalization
from .defoc import f_remain

# Set the default font to Arial
import matplotlib
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = 'Arial'

# Default binning scheme
DEFAULT_DIFF_COEFS = np.logspace(-2.0, 2.0, 301)

## PLOT UTILITIES

def save_png(out_png, dpi=600):
    """
    Save a matplotlib.figure.Figure to a PNG.

    args
    ----
        out_png         :   str, out path
        dpi             :   int, resolution

    """
    plt.tight_layout()
    plt.savefig(out_png, dpi=dpi)
    plt.close()
    if sys.platform == "darwin":
        os.system("open {}".format(out_png))

def kill_ticks(axes, spines=False, grid=False):
    """
    Remove the ticks from a matplotlib Axes.

    args
    ----
        axes        :   matplotlib.axes.Axes
        spines      :   bool, also remove spines
        grid        :   bool, also remove the grid

    """
    axes.set_xticks([])
    axes.set_yticks([])
    if spines:
        for s in ['top', 'bottom', 'left', 'right']:
            axes.spines[s].set_visible(False)
    if grid:
        axes.grid(False)

def circular_filter(im, radius):
    """
    Convolve an image with an circular kernel.

    args
    ----
        im          :   2D ndarray
        radius      :   float, radius of kernel in pixels

    returns
    -------
        2D ndarray of shape im.shape

    """
    # Build the kernel
    N, M = im.shape 
    Y, X = np.indices((N, M))
    kernel = (((Y-N//2)**2 + (X-M//2)**2) <= radius**2).astype(np.float64)
    kernel /= kernel.sum()

    # Convolve with the image
    return np.fft.fftshift(np.fft.irfft2(
        np.fft.rfft2(im) * np.fft.rfft2(kernel), s=im.shape
    ))

def try_add_scalebar(axes, pixel_size, units="um", fontsize=8,
    location="lower left"):
    """
    If the *matplotlib_scalebar* package is available, add a 
    scalebar. Otherwise do nothing.

    args
    ----
        axes        :   matplotlib.axes.Axes
        pixel_size  :   float
        units       :   str
        fontsize    :   int
        location    :   str, "upper left", "lower left",
                        "upper right", or "lower right"

    returns
    -------
        None

    """
    try:
        from matplotlib_scalebar.scalebar import ScaleBar 
        scalebar = ScaleBar(pixel_size, units, location=location,
            frameon=False, color="w", font_properties={'size': fontsize})
        axes.add_artist(scalebar)
    except ModuleNotFoundError:
        pass 

def add_log_scale_imshow(axes, diff_coefs, fontsize=None):
    """
    Add a log x-axis to a plot produced by matplotlib.axes.Axes.imshow.

    args
    ----
        axes        :   matplotlib.axes.Axes
        diff_coefs  :   1D ndarray
        fontsize    :   int

    returns
    -------
        None; modifies *axes* directly

    """
    diff_coefs = np.asarray(diff_coefs)
    K = diff_coefs.shape[0]
    d_min = min(diff_coefs)
    d_max = max(diff_coefs)

    # Linear range of the axes
    xlim = axes.get_xlim()
    lin_span = xlim[1] - xlim[0]

    # Determine the number of log-10 units (corresponding
    # to major ticks)
    log_diff_coefs = np.log10(diff_coefs)
    first_major_tick = int(log_diff_coefs[0])
    major_tick_values = [first_major_tick]
    c = first_major_tick
    while log_diff_coefs.max() > c:
        c += 1
        major_tick_values.append(c)
    n_major_ticks = len(major_tick_values)

    # Convert between the linear and log scales
    log_span = log_diff_coefs[-1] - log_diff_coefs[0]
    m = lin_span / log_span 
    b = xlim[0] - m * log_diff_coefs[0]
    def convert_log_to_lin_coord(log_coord):
        return m * log_coord + b

    # Choose the location of the major ticks
    major_tick_locs = [convert_log_to_lin_coord(coord) \
        for coord in major_tick_values]

    # Major tick labels
    major_tick_labels = ["$10^{%d}$" % int(j) for j in major_tick_values]

    # Minor ticks 
    minor_tick_decile = np.log10(np.arange(1, 11))
    minor_tick_values = []
    for i in range(int(major_tick_values[0])-1, int(major_tick_values[-1])+2):
        minor_tick_values += list(minor_tick_decile + i)
    minor_tick_locs = [convert_log_to_lin_coord(v) for v in minor_tick_values]
    minor_tick_locs = [i for i in minor_tick_locs if ((i >= xlim[0]) and (i <= xlim[1]))]

    # Set the ticks
    axes.set_xticks(major_tick_locs, minor=False)
    axes.set_xticklabels(major_tick_labels, fontsize=fontsize)
    axes.set_xticks(minor_tick_locs, minor=True)

## MAIN PLOT TOOLS

def plot_diff_coef_spectrum(posterior, diff_coefs, log_scale=True,
    out_png=None, d_err=None, ylim=None, axes=None,
    truncate_immobile_frac=False):
    """
    Make a plot of the posterior distribution over the 
    diffusion coefficient. 

    args
    ----
        posterior       :   1D ndarray of shape (n_bins,),
                            the posterior density
        diff_coefs      :   1D ndarray of shape (n_bins+1,),
                            the edges of each diffusion
                            coefficient bin in squared microns
                            per second
        log_scale       :   bool, use a logarithmic scale for 
                            the diffusion coefficient
        out_png         :   str, save path for figure
        d_err           :   float, the apparent speed of immobile
                            objects due to localization error
        ylim            :   (float, float), the y-axis limits
        axes            :   matplotlib.axes.Axes, the axis to 
                            use for the plot. If not given, a 
                            new axis is generated.
        truncate_immobile_frac  :   bool, truncate the y-axis
                            upper limit so that the plot isn't
                            dominated by the peak at the immobile
                            fraction. If *ylim* is set, this is 
                            superceded.

    returns
    -------
        If *out_png* is set, saves directly to a PNG.

        Otherwise returns
        (
            matplotlib.figure.Figure,
            matplotlib.axes.Axes
        )

    """
    fontsize = 7

    # Figure layout
    if axes is None:
        fig, axes = plt.subplots(figsize=(4, 1.5))

    # Use either the midpoint or the geometric mean of each 
    # bin, depending on whether we're working in linear or 
    # log space
    if log_scale:
        d = np.sqrt(diff_coefs[1:] * diff_coefs[:-1])
    else:
        d = 0.5 * (diff_coefs[1:] * diff_coefs[:-1])

    # Plot the posterior density
    axes.plot(d, posterior, color="k", linestyle="-", label=None)

    # Make a vertical dotted line at a user-defined location
    if not d_err is None:
        axes.plot([d_err, d_err], [0, posterior.max()*1.3], color="k",
            linestyle="--", label="Loc error limit")
        # axes.legend(frameon=False, loc="upper right", 
        #     prop={"size": min(fontsize, 8)})

    # Log scale
    if log_scale:
        axes.set_xscale("log")

    # Axis labels
    axes.set_xlabel("Diffusion coefficient ($\mu$m$^{2}$ s$^{-1}$)",
        fontsize=fontsize)
    axes.set_ylabel("Posterior mean\ndensity", fontsize=fontsize)

    # Limit the y-axis 
    if not ylim is None:
        axes.set_ylim(ylim)
    else:
        if truncate_immobile_frac:
            upper_ylim = posterior[d>0.05].max() * 1.3
            axes.set_ylim((0, upper_ylim))
        else:
            axes.set_ylim((0, axes.get_ylim()[1]))
    axes.set_xlim((diff_coefs.min(), diff_coefs.max()))

    # Set tick font size
    axes.tick_params(labelsize=fontsize)

    # Save, if desired
    if not out_png is None:
        save_png(out_png, dpi=800)
    else:
        return fig, axes 

def plot_likelihood_by_file(track_csvs, diff_coefs=None, posterior=None,
    frame_interval=0.00748, pixel_size_um=0.16, loc_error=0.03, start_frame=None,
    pos_cols=["y", "x"], max_jumps_per_track=None, likelihood_mode="point",
    group_labels=None, vmax=None, out_png=None, log_x_axis=True,
    label_by_file=False, by_jump=False, scale_colors_by_group=False,
    vmax_perc=99, dz=None, out_csv=None):
    """
    Plot the diffusion coefficient likelihood for several different
    tracking files alongside each other, for comparison.

    The result is a heat plot where each row corresponds to a separate
    set of trajectories, and the columns represent different diffusion
    coefficients or bins of diffusion coefficients. 

    note
    ----
        *track_csvs*, the paths to the files with the trajectories to use,
        can be specified in one of two formats:

        A list of paths. In this case, a single subplot is generated with
        each row corresponding to one file.

        A list of list of paths. In this case, each sublist produces a 
        separate subplot. The subplots are spatially separated and can 
        be given titles with *group_labels*. For instance, this is useful to
        compare between conditions.

    args
    ----
        track_csvs          :   list of str ~or~ list of list of str,
                                paths to CSVs with raw trajectories
        diff_coefs          :   1D ndarray, the set of diffusion 
                                coefficients at which to evaluate the 
                                likelihoods. If not specified, defaults
                                the same default binning scheme as 
                                dpsp.
        posterior           :   1D ndarray, the posterior occupations of
                                each diffusion coefficient. If *None*,
                                then all diffusion coefficients are weighted
                                equally.
        frame_interval      :   float, seconds
        pixel_size_um       :   float, microns
        loc_error           :   float, root variance in microns
        start_frame         :   int, ignore jumps before this frame
        pos_cols            :   list of str, columns in the trajectory 
                                CSVs with spatial coordinates in pixels
        max_jumps_per_track :   str, the maximum number of jumps to consider
                                from any single trajectory
        likelihood_mode     :   str, either "binned" or "point", the type
                                of likelihood to calculate
        group_labels        :   list of str, subplot titles to use 
        vmax                :   float, upper color limit
        out_png             :   str, output file
        log_x_axis          :   bool, use a log scale for the x-axis
        label_by_file       :   bool, indicate the origin file for each row
        by_jump             :   bool, compute likelihoods on a jump-by-jump 
                                basis rather than a trajectory-by-trajectory
                                basis. This removes the assumption that 
                                trajectories remain in the same diffusive state,
                                at the cost of resolution.
        scale_colors_by_group:  bool, if using a list-of-lists for *track_csvs*,
                                scale the color map for each subgroup separately.
        vmax_perc           :   float between 0 and 100, percentile of likelihood
                                values to use as the upper limit for the color map.
                                If setting the upper limit for the color map 
                                manually with *vmax*, this has no meaning.
        dz                  :   float, focal depth in microns. If set, 
                                a defocalization correction is applied to account
                                for the loss of the free states.
        out_csv             :   str, a CSV to which to save the raw likelihoods
                                for custom analysis 

    returns
    -------
        If *out_png* is specified, saves to that PNG. Otherwise returns
        (
            matplotlib.figure.Figure,
            matplotlib.axes.Axes
        )

    """
    # Default binning scheme
    if diff_coefs is None:
        diff_coefs = DEFAULT_DIFF_COEFS

    # Coerce into ndarray
    diff_coefs = np.asarray(diff_coefs)
    if not posterior is None:
        posterior = np.asarray(posterior)

    # Number of diffusion coefficient bins
    if likelihood_mode == "binned":
        n_bins = diff_coefs.shape[0] - 1
        if not posterior is None:
            assert posterior.shape[0] == n_bins, \
                "posterior shape incompatible for likelihood mode `binned`"
    elif likelihood_mode == "point":
        n_bins = diff_coefs.shape[0]
        if not posterior is None:
            assert posterior.shape[0] == n_bins, \
                "posterior shape incompatible for likelihood mode `point`"

    # Determine the type of plot to make
    if isinstance(track_csvs[0], str) or (isinstance(track_csvs[0], list) \
        and len(track_csvs) == 1):

        # Number of sets of trajectories
        n = len(track_csvs)

        # Calculate the likelihoods of each diffusion coefficient
        L = np.zeros((n, n_bins), dtype=np.float64)
        L_matrices = []
        for i, track_csv in enumerate(track_csvs):
            tracks = pd.read_csv(track_csv)

            # Evaluate likelihoods of each diffusion coefficient
            # for this set of trajectories
            track_likelihoods, n_jumps, track_indices = likelihood_matrix(
                tracks,
                diff_coefs,
                posterior=posterior, 
                frame_interval=frame_interval,
                pixel_size_um=pixel_size_um,
                loc_error=loc_error,
                start_frame=start_frame,
                pos_cols=pos_cols, 
                max_jumps_per_track=max_jumps_per_track,
                likelihood_mode=likelihood_mode,
                by_jump=by_jump
            )

            # Scale likelihoods by the number of jumps per trajectory
            # and aggregate across all trajectories
            L[i,:] = (track_likelihoods.T * n_jumps).T.sum(axis=0)

        # Correct for defocalization, if applicable
        if (not dz is None) and (not dz is np.inf):
            corr = np.zeros(L.shape[1], dtype=np.float64)
            for j, D in enumerate(diff_coefs):
                corr[j] = f_remain(D, 1, frame_interval, dz)[0]
            L = L / corr 

        # Normalize across all diffusion coefficients for each file
        L = (L.T / L.sum(axis=1)).T 

        # Save a reference to the likelihood matrix for later saving, if desired
        if not out_csv is None:
            L_matrices.append(L)

        # Plot layout
        y_ext = 2.0
        x_ext = 7.0
        fig, ax = plt.subplots(figsize=(x_ext, y_ext))
        fontsize = 8
        if vmax is None:
            vmax = np.percentile(L, vmax_perc)

        # Make the primary plot
        S = ax.imshow(L, vmin=0, vmax=vmax,
            extent=(0, x_ext, 0, y_ext),
            origin="lower")

        # Colorbar
        cbar = plt.colorbar(S, ax=ax, shrink=0.6)
        cbar.ax.tick_params(labelsize=fontsize)
        cbar.set_label("Aggregate likelihood", rotation=90)

        # Make the x-axis a log scale
        if log_x_axis:
            add_log_scale_imshow(ax, diff_coefs, fontsize=fontsize)

        # y labels
        if label_by_file:
            basenames = [os.path.basename(f) for f in track_csvs]
            ax.set_ylabel(None)
            yticks = np.arange(n) * y_ext / n + y_ext / (n * 2.0)
            ax.set_yticks(yticks)
            ax.set_yticklabels(basenames, fontsize=fontsize)
        else:
            ax.set_yticks([])
            ax.set_ylabel("File", fontsize=fontsize)

        # x label
        ax.set_xlabel("Diffusion coefficient ($\mu$m$^{2}$ s$^{-1}$)", 
            fontsize=fontsize)

        # Axis title
        title = "Prior likelihood" if posterior is None else "Posterior likelihood"
        ax.set_title(title, fontsize=fontsize)

        # Save these likelihoods, if desired
        if not out_csv is None:
            n_files, n_bins = L.shape
            M = n_files * n_bins 
            out_df_cols = ["origin_file", "diff_coef", "likelihood"]
            out_df = pd.DataFrame(index=np.arange(M), columns=out_df_cols)           

            for i in range(n_files):
                start_bin = i * n_bins 
                stop_bin = (i + 1) * n_bins 
                match = out_df.index.isin(range(start_bin, stop_bin))

                out_df.loc[match, "origin_file"] = track_csvs[i]
                out_df.loc[match, "likelihood"] = L[i,:]
                if likelihood_mode == "binned":
                    out_df.loc[match, "diff_coef"] = diff_coefs[:-1]
                elif likelihood_mode == "point":
                    out_df.loc[match, "diff_coef"] = diff_coefs 

            out_df.to_csv(out_csv, index=False)

    elif isinstance(track_csvs[0], list):

        # Determine the number of groups
        n_groups = len(track_csvs)

        # Plot layout
        y_ext_subplot = 2.0
        y_ext = 2.0 * n_groups 
        x_ext = 7.0
        fig, ax = plt.subplots(n_groups, 1, figsize=(x_ext, y_ext),
            sharex=True)
        fontsize = 10

        # Calculate the likelihood matrix for each group separately
        L_matrices = []
        for group_idx in range(n_groups):

            group_track_csvs = track_csvs[group_idx]
            n_files = len(group_track_csvs)

            L = np.zeros((n_files, n_bins), dtype=np.float64)
            for i, track_csv in enumerate(group_track_csvs):
                tracks = pd.read_csv(track_csv)

                # Evaluate likelihoods of each diffusion coefficient
                # for this set of trajectories
                track_likelihoods, n_jumps, track_indices = likelihood_matrix(
                    tracks,
                    diff_coefs,
                    posterior=posterior, 
                    frame_interval=frame_interval,
                    pixel_size_um=pixel_size_um,
                    loc_error=loc_error,
                    pos_cols=pos_cols, 
                    max_jumps_per_track=max_jumps_per_track,
                    likelihood_mode=likelihood_mode
                )

                # Scale likelihoods by the number of jumps per trajectory
                # and aggregate across all trajectories
                L[i,:] = (track_likelihoods.T * n_jumps).T.sum(axis=0)

            # Correct for defocalization, if applicable
            if (not dz is None) and (not dz is np.inf):
                corr = np.zeros(L.shape[1], dtype=np.float64)
                for j, D in enumerate(diff_coefs):
                    corr[j] = f_remain(D, 1, frame_interval, dz)[0]
                L = L / corr 

            # Normalize across all diffusion coefficients for each file
            L = (L.T / L.sum(axis=1)).T 
            L_matrices.append(L)

            print("Finished with group %d..." % group_idx)

        # Global color scalar
        if (not vmax is None):
            vmax = [vmax for i in range(len(L_matrices))]
        elif (vmax is None) and (scale_colors_by_group):
            vmax = [np.percentile(L, vmax_perc) for L in L_matrices]
        elif (vmax is None) and (not scale_colors_by_group):
            vmax = max([np.percentile(L, vmax_perc) for L in L_matrices])
            vmax = [vmax for i in range(len(L_matrices))]

        # Make the primary plot
        for i, L in enumerate(L_matrices):
            S = ax[i].imshow(L, vmin=0, vmax=vmax[i], extent=(0, x_ext, 0, y_ext_subplot),
                origin="lower")
            cbar = plt.colorbar(S, ax=ax[i], shrink=0.6)
            cbar.ax.tick_params(labelsize=fontsize)
            cbar.set_label("Aggregate likelihood", rotation=90)

            # Make the x-axis a log scale
            if log_x_axis:
                add_log_scale_imshow(ax[i], diff_coefs, fontsize=fontsize)

            # y labels
            if label_by_file:
                group_track_csvs = track_csvs[i]
                basenames = [os.path.basename(f) for f in group_track_csvs]
                n_files = len(group_track_csvs)
                ax[i].set_ylabel(None)
                yticks = np.arange(n_files) * y_ext_subplot / n_files + \
                    y_ext_subplot / (n_files * 2.0)
                ax[i].set_yticks(yticks)
                ax[i].set_yticklabels(basenames, fontsize=fontsize)
            else:
                ax[i].set_yticks([])
                ax[i].set_ylabel("File", fontsize=fontsize)

            # Axis title
            if not group_labels is None:
                ax[i].set_title(group_labels[i], fontsize=fontsize)
            else:
                title = "Prior likelihood" if posterior is None else "Posterior likelihood"
                ax[0].set_title(title, fontsize=fontsize)

        # x label
        ax[-1].set_xlabel("Diffusion coefficient ($\mu$m$^{2}$ s$^{-1}$)", 
            fontsize=fontsize)

        # Save these likelihood matrices, if desired
        if not out_csv is None:

            n_groups = len(L_matrices)
            tot_n_files = sum([L.shape[0] for L in L_matrices])
            tot_n_bins = sum([L.shape[1] for L in L_matrices])

            # Output dataframe
            M = sum([L.shape[0] * L.shape[1] for L in L_matrices])
            out_df_cols = ["group_idx", "group_label", "diff_coef", "origin_file", "likelihood"]
            out_df = pd.DataFrame(index=np.arange(M), columns=out_df_cols)

            # Current DataFrame index 
            c = 0

            # Iterative through the file groups 
            for i, L in enumerate(L_matrices):

                # Number of files corresponding to this file group
                n_files, n_bins = L.shape

                for j in range(n_files):

                    # The set of output DataFrame indices corresponding to this file
                    match = out_df.index.isin(range(c, c+n_bins))

                    # The index of the corresponding file group
                    out_df.loc[match, "group_idx"] = i 

                    # The label of the corresponding file group
                    if not group_labels is None:
                        out_df.loc[match, "group_label"] = group_labels[i]

                    # The diffusion coefficient corresponding to the likelihoods
                    if likelihood_mode == "binned":
                        out_df.loc[match, "diff_coef"] = diff_coefs[:-1]
                    elif likelihood_mode == "point":
                        out_df.loc[match, "diff_coef"] = diff_coefs

                    # The actual likelihood values
                    out_df.loc[match, "likelihood"] = L[j,:]

                    # The origin file
                    out_df.loc[match, "origin_file"] = track_csvs[i][j]

                    # Increment the index 
                    c += n_bins 

            # Save to the CSV
            out_df.to_csv(out_csv, index=False)

    # Save if desired
    if not out_png is None:
        save_png(out_png, dpi=800)
    else:
        return fig, ax 

def plot_likelihood_fbm(*track_csvs, hurst_pars=None, diff_coefs=None,
    posterior=None, frame_interval=0.00748, pixel_size_um=0.16, loc_error=0.03, 
    start_frame=None, pos_cols=["y", "x"], max_jumps_per_track=None,
    min_jumps_per_track=1, vmax=None, out_png=None, log_x_axis=True,
    vmax_perc=99, weight_by="jump", cmap="viridis", fontsize=10,
    axes=None, dz=None):
    """
    Plot the likelihood function for fractional Brownian motion as a 
    function of the Hurst parameter and diffusion coefficient. All 
    trajectories are pooled to evaluate the likelihood.

    args
    ----
        tracks_csvs         :   variadic set of str, paths to 
                                trajectory files to use
        hurst_pars          :   1D ndarray, the set of Hurst 
                                parameters at which to evaluate
                                the likelihoods. If not set, 
                                goes to a default scheme.
        diff_coefs          :   1D ndarray, the set of diffusion
                                coefficients at which to evaluate
                                the likelihoods. If not set, 
                                goes to a default scheme.
        posterior           :   2D ndarray of shape (n_hurst,
                                n_diff_coefs), the posterior
                                probabilities for each of the 
                                states. If not set, assumes a 
                                uniform prior.
        frame_interval      :   float, seconds
        pixel_size_um       :   float, microns
        loc_error           :   float, root variance in microns
        start_frame         :   int, disregard jumps before this 
                                frame
        pos_cols            :   list of str
        max_jumps_per_track :   int
        min_jumps_per_track :   int
        vmax                :   float, upper limit for the 
                                color scheme
        out_png             :   str, file to save figure to
        log_x_axis          :   bool, use a log x-axis
        vmax_perc           :   float, the percentile of likelihood
                                to use to set the upper color scheme
                                limit, if *vmax* is None
        weight_by           :   str, either "jump" or "trajectory"
        cmap                :   str
        fontsize            :   int
        axes                :   matplotlib.axes.Axes, an existing axes
                                to plot to
        dz                  :   float, focal depth in microns. If set,
                                a defocalization correction is applied.

    returns
    -------
        If *out_png* is set, saves directly to a PNG file. 
        Otherwise returns
        (
            matplotlib.figure.Figure,
            matplotlib.axes.Axes
        )

    """
    # Load all of the trajectories from the target files
    tracks = load_tracks(*track_csvs, start_frame=start_frame,
        drop_singlets=True)

    # Use the default binning scheme, if none is provided
    if (diff_coefs is None):
        diff_coefs = DEFAULT_DIFF_COEFS.copy()
    if (hurst_pars is None):
        hurst_pars = np.arange(0.05, 1.0, 0.05)

    # Calculate the likelihoods for each state
    track_likelihoods, n_jumps, track_indices = likelihood_matrix_fbm(
        tracks, hurst_pars, diff_coefs, posterior=posterior, 
        frame_interval=frame_interval, pixel_size_um=pixel_size_um,
        loc_error=loc_error, start_frame=start_frame, pos_cols=pos_cols,
        max_jumps_per_track=max_jumps_per_track, 
        min_jumps_per_track=min_jumps_per_track)

    # If not given a matplotlib.axes.Axes, make one
    if axes is None:
        fig, axes = plt.subplots(figsize=(5, 2))

    # Scale the trajectory likelihoods
    if weight_by == "jump":
        track_likelihoods = (track_likelihoods.T * n_jumps).T 

    # Sum the likelihoods across all trajectories
    sum_L = track_likelihoods.sum(axis=0)

    # Calculate the color map maximum, if not provided
    if vmax is None:
        vmax = np.percentile(sum_L, vmax_perc)

    # Plot the result
    x_ext = 5.0
    y_ext = 1.8
    S = axes.imshow(sum_L, cmap=cmap, vmin=0, vmax=vmax,
        extent=(0, x_ext, 0, y_ext), origin="lower")

    # Color scale
    cbar = plt.colorbar(S, ax=axes, shrink=0.6)
    cbar.ax.tick_params(labelsize=fontsize)
    cbar.set_label("Likelihood", rotation=90, fontsize=fontsize)

    # Make the x-axis in terms of the log diffusion coefficients
    if log_x_axis:
        add_log_scale_imshow(axes, diff_coefs, fontsize=fontsize)
    else:
        n_labels = 7
        nD = len(diff_coefs)
        m = nD // n_labels 
        xticks = np.arange(nD) * x_ext / nD + x_ext / (nD * 2.0)
        axes.set_xticks(xticks)
        axes.set_xticklabels(np.asarray(diff_coefs)[m//2::m].round(2), fontsize=fontsize)
    axes.set_xlabel("Diffusion coefficient ($\mu$m$^{2}$ s$^{-1}$)",
        fontsize=fontsize)

    # y-axis labels
    n_labels = 7
    nH = len(hurst_pars)
    y_indices = np.arange(nH)
    m = nH // n_labels 
    yticks = np.arange(nH) * y_ext / nH + y_ext / (nH * 2.0)
    yticks = yticks[m//2::m]
    axes.set_yticks(yticks)
    axes.set_yticklabels(np.asarray(hurst_pars)[m//2::m].round(2), fontsize=fontsize)
    axes.set_ylabel("Hurst parameter")

    # Save, if desired
    if (not out_png is None):
        save_png(out_png, dpi=800)
    else:
        return plt.gcf(), axes 

def plot_spatial_likelihood(track_csv, diff_coefs, posterior=None, bin_size_um=0.05,
    filter_kernel_um=0.12, frame_interval=0.00748, pixel_size_um=0.16,
    loc_error=0.03, start_frame=None, pos_cols=["y", "x"], max_jumps_per_track=None,
    cmap="viridis", vmax=None, fontsize=10, out_png=None,
    normalize_by_loc_density=False, normalize_diff_coefs_separately=False):
    """
    Visualize the likelihood of each of a set of diffusion coefficients
    as a function of the spatial position of each trajectory. Additionally,
    this plots the localization density.

    args
    ----
        track_csv       :   str, path to a CSV with trajectories
        diff_coefs      :   1D ndarray, the set of diffusion coefficients
                            at which to evaluate the likelihood(s)
        posterior       :   1D ndarray, the posterior probability for 
                            each diffusion coefficient
        bin_size_um     :   float, size of the bins to use when making
                            the spatial histogram in microns
        filter_kernel_um:   float, size of the uniform filter to use 
                            in microns
        frame_interval  :   float, seconds
        pixel_size_um   :   float, microns
        loc_error       :   float, root variance in microns
        start_frame     :   int, ignore jumps before this frame
        pos_cols        :   list of str, the columns in *tracks* with the
                            spatial coordinates of each detection in 
                            pixels
        max_jumps_per_track :   int, the maximum jumps to consider for
                                each trajectory
        cmap            :   str, color map
        vmax            :   float, the upper likelihood to use for 
                            color scaling
        fontsize        :   int
        out_png         :   str, path to save plot to.
        normalize_by_loc_density    :   bool, normalize the result
                            by the number of localizations in the local
                            neighborhood, so that the resulting color
                            reflects the probability to pick a molecule
                            with a given diffusion coefficient from that
                            area.
        normalize_diff_coefs_separately : bool, use a separate color
                            scale for each diffusion coefficient.

    returns
    -------
        If *out_png* is specified, saves to that path as a PNG.
        Otherwise returns
        (
            matplotlib.figure.Figure,
            matplotlib.axes.Axes
        )

    """
    M = len(diff_coefs) + 1
    diff_coef_indices = np.arange(len(diff_coefs))
    likelihood_cols = ["likelihood_%d" % j for j in diff_coef_indices]
    diff_coefs = np.asarray(diff_coefs)

    # Load trajectories
    T = pd.read_csv(track_csv)

    # Remove singlets
    tracks = track_length(T)
    tracks = tracks[tracks["track_length"] > 1]

    # Calculate likelihoods of each diffusion coefficient, given
    # each set of trajectories
    L, n_jumps, track_indices = likelihood_matrix(
        tracks,
        diff_coefs,
        posterior=posterior,
        frame_interval=frame_interval,
        pixel_size_um=pixel_size_um,
        loc_error=loc_error,
        start_frame=start_frame,
        pos_cols=pos_cols,
        max_jumps_per_track=max_jumps_per_track,
        likelihood_mode="point"
    )

    # Scale by posterior state occupations
    if not posterior is None:
        posterior = np.asarray(posterior)
        L = L * posterior 
        L = (L.T / L.sum(axis=1)).T 

    # Map likelihoods back to origin trajectories
    L = pd.DataFrame(L, columns=diff_coef_indices, index=track_indices)
    for i in diff_coef_indices:
        tracks[likelihood_cols[i]] = tracks["trajectory"].map(L[i])

    # Only consider points for which the likelihood is defined
    tracks = tracks.loc[~pd.isnull(tracks[likelihood_cols[0]]), :]

    # Plot layout
    if np.sqrt(M) % 1.0 == 0:
        r = int(np.sqrt(M))
        ny = nx = r 
    else:
        r = int(np.sqrt(M)) + 1
        nx = r 
        ny = M // r + 1
    fig, ax = plt.subplots(ny, nx, figsize=(nx*3, ny*3),
        sharex=True, sharey=True)

    # Convert from pixels to um
    tracks[pos_cols] = tracks[pos_cols] * pixel_size_um 

    # Determine the extent of the field of view
    y_min = tracks[pos_cols[0]].min() - 3.0 * pixel_size_um
    y_max = tracks[pos_cols[0]].max() + 3.0 * pixel_size_um
    x_min = tracks[pos_cols[1]].min() - 3.0 * pixel_size_um
    x_max = tracks[pos_cols[1]].max() + 3.0 * pixel_size_um
    y_span = y_max - y_min 
    x_span = x_max - x_min

    # Bins for computing histograms
    bins_y = np.arange(y_min, y_max, bin_size_um)
    bins_x = np.arange(x_min, x_max, bin_size_um)
    n_bins_y = bins_y.shape[0] - 1
    n_bins_x = bins_x.shape[0] - 1
    filter_kernel = filter_kernel_um / bin_size_um

    # Plot localization density
    loc_density = np.histogram2d(
        tracks[pos_cols[0]],
        tracks[pos_cols[1]],
        bins=(bins_y, bins_x)
    )[0].astype(np.float64)
    density = gaussian_filter(loc_density, filter_kernel)
    S = ax[0,0].imshow(density, cmap="gray", vmin=0, 
        vmax=np.percentile(density, 99))
    cbar = plt.colorbar(S, ax=ax[0,0], shrink=0.5)
    cbar.ax.tick_params(labelsize=fontsize)
    kill_ticks(ax[0,0])
    ax[0,0].set_title("Localization density", fontsize=fontsize)
    try_add_scalebar(ax[0,0], bin_size_um, "um", fontsize=fontsize)

    # Calculate a histogram of all localizations weighted by 
    # the likelihood of each diffusion coefficient
    H = np.zeros((len(diff_coefs), n_bins_y, n_bins_x), dtype=np.float64)
    for i, diff_coef in enumerate(diff_coefs):

        # Calculate a histogram of all localizations weighted by 
        # the likelihood of this particular diffusion coefficient
        H[i,:,:] = np.histogram2d(
            tracks[pos_cols[0]],
            tracks[pos_cols[1]], 
            bins=(bins_y, bins_x),
            weights=np.asarray(tracks[likelihood_cols[i]])
        )[0].astype(np.float64)

        # Smooth
        H[i,:,:] = gaussian_filter(H[i,:,:], filter_kernel)

    # Normalize by the localization density, if desired. If 
    # doing this, only show pixels that actually have enough
    # nearby localizations to compute
    if normalize_by_loc_density:
        norm = H.sum(axis=0)
        nonzero = norm > 0.000001
        for i in range(len(diff_coefs)):
            H[i,:,:][nonzero] = H[i,:,:][nonzero] / norm[nonzero]
            H[i,:,:][~nonzero] = 0

    # If *normalize_diff_coefs_separately* is set, then use 
    # a separate color palette for each diffusion coefficient
    if normalize_diff_coefs_separately:
        vmax = [np.percentile(H[i,:,:], 99) for i in range(len(diff_coefs))]
    else:
        vmax = np.percentile(H, 99)
        vmax = [vmax for i in range(len(diff_coefs))]

    # Plot the likelihood maps
    for i, diff_coef in enumerate(diff_coefs):

        # The subplot to use
        j = i + 1
        ax_x = j % nx 
        ax_y = j // nx 

        # Make an imshow plot
        S = ax[ax_y, ax_x].imshow(H[i,:,:], cmap=cmap, vmin=0, vmax=vmax[i])

        # Color bar
        cbar = plt.colorbar(S, ax=ax[ax_y, ax_x], shrink=0.5)
        cbar.ax.tick_params(labelsize=fontsize)

        # Title
        ax[ax_y, ax_x].set_title(
            "%.3f $\mu$m$^{2}$ s$^{-1}$" % diff_coef,
            fontsize=fontsize
        )

        # Scalebar
        try_add_scalebar(ax[ax_y, ax_x], bin_size_um, units="um",
            fontsize=fontsize)

        # Remove ticks
        kill_ticks(ax[ax_y, ax_x])

    # Make the rest of the subplots invisible
    for j in range(len(diff_coefs)+1, ny * nx):
        ax_x = j % nx 
        ax_y = j // nx        
        kill_ticks(ax[ax_y, ax_x], spines=True, grid=True)

    if not out_png is None:
        save_png(out_png, dpi=1000)
    else:
        return fig, ax 

