"""
Agentpy Analysis Module
Content: Sensitivity and interactive analysis, animation, visualization
"""

import matplotlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from SALib.analyze import sobol

from .tools import make_list, param_tuples_to_salib


def _sobol_set_df_index(df, p_keys, measure):
    df['parameter'] = p_keys
    df['measure'] = measure
    df.set_index(['measure', 'parameter'], inplace=True)


def sensitivity_sobol(output, param_ranges, measures=None,
                      calc_second_order=False, **kwargs):
    """ Calculates Sobol Sensitivity Indices and adds them to the output,
    using :func:`SALib.analyze.sobol.analyze`. To work correctly,
    data must be from an experiment with a parameter sample that was
    generated by :func:`sample_saltelli`.

    Arguments:
        output (DataDict): The output of an experiment that was set to only
            one iteration (default) and used a parameter sample that was
            generated with :func:`sample_saltelli`.
        param_ranges (dict): The same dictionary that was used for the
            generation of the parameter sample with :func:`sample_saltelli`.
        measures (str or list of str, optional): The measures that should
            be used for the analysis. If none are passed, all are used.
        calc_second_order (bool, optional): Whether to calculate second order
            indices (default False). Value must be the same as the one used
            to generate the parameter sample with :func:`sample_saltelli`.
        **kwargs: Will be forwarded to :func:`SALib.analyze.sobol.analyze`.
    """

    # STEP 1 - Convert param_ranges to SALib Format
    param_ranges_tuples = {k: v for k, v in param_ranges.items()
                           if isinstance(v, tuple)}
    param_ranges_salib = param_tuples_to_salib(param_ranges_tuples)

    # STEP 2 - Calculate Sobol Sensitivity Indices
    if measures is None:
        measures = output.measures.columns
    if isinstance(measures, str):
        measures = [measures]
    p_keys = output._combine_pars(varied=True, fixed=False).keys()
    dfs_list = [[] for _ in range(4 if calc_second_order else 2)]

    for measure in measures:
        y = np.array(output.measures[measure])
        si = sobol.analyze(param_ranges_salib, y, calc_second_order, **kwargs)

        # Make dataframes out of S1 and ST sensitivities
        keyss = [['S1', 'ST'], ['S1_conf', 'ST_conf']]
        for keys, dfs in zip(keyss, dfs_list[0:2]):
            s = {k[0:2]: v for k, v in si.items() if k in keys}
            df = pd.DataFrame(s)
            _sobol_set_df_index(df, p_keys, measure)
            dfs.append(df)

        # Make dataframes out S2 sensitivities
        if calc_second_order:
            for key, dfs in zip(['S2', 'S2_conf'], dfs_list[2:4]):
                df = pd.DataFrame(si[key])
                _sobol_set_df_index(df, p_keys, measure)
                dfs.append(df)

    # Combine dataframes for each measure
    output['sensitivity'] = pd.concat(dfs_list[0])
    output['sensitivity_conf'] = pd.concat(dfs_list[1])

    if calc_second_order:

        # Add Second-Order to Output
        dfs_si = [output['sensitivity'], pd.concat(dfs_list[2])]
        dfs_si_conf = [output['sensitivity_conf'], pd.concat(dfs_list[3])]
        output['sensitivity'] = pd.concat(dfs_si, axis=1)
        output['sensitivity_conf'] = pd.concat(dfs_si_conf, axis=1)

        # Create Multi-Index for Columns
        arrays = [["S1", "ST"] + ["S2"] * len(p_keys), [""] * 2 + list(p_keys)]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples, names=["order", "parameter"])
        output['sensitivity'].columns = index
        output['sensitivity_conf'].columns = index.copy()

    return output


def animate(model, fig, axs, plot, steps=None, seed=None,
            skip=0, fargs=(), **kwargs):
    """ Returns an animation of the model simulation,
    using :func:`matplotlib.animation.FuncAnimation`.

    Arguments:
        model (Model): The model instance.
        fig (matplotlib.figure.Figure): Figure for the animation.
        axs (matplotlib.axes.Axes or list): Axis or list of axis of the figure.
        plot (function): Function that takes `(model, ax, *fargs)`
            and creates the desired plots on each axis at each time-step.
        steps(int, optional):
            Maximum number of steps for the simulation to run.
            If none is given, the parameter 'Model.p.steps' will be used.
            If there is no such parameter, 'steps' will be set to 1000.
        seed (int, optional):
            Seed to set for :obj:`Model.random` at the beginning of the simulation.
            If none is given, the parameter 'Model.p.seed' will be used.
            If there is no such parameter, as random seed will be set.
        skip (int, optional): Number of rounds to skip before the
            animation starts (default 0).
        fargs (tuple, optional): Forwarded fo the `plot` function.
        **kwargs: Forwarded to :func:`matplotlib.animation.FuncAnimation`.

    Examples:
        An animation can be generated as follows::

            def my_plot(model, ax):
                pass  # Call pyplot functions here
            
            fig, ax = plt.subplots() 
            my_model = MyModel(parameters)
            animation = ap.animate(my_model, fig, ax, my_plot)

        One way to display the resulting animation object in Jupyter::

            from IPython.display import HTML
            HTML(animation.to_jshtml())
    """

    model.run_setup(steps, seed)
    model.create_output()
    pre_steps = 0

    for _ in range(skip):
        model.run_step()

    def frames():
        nonlocal model, pre_steps
        if model._stop is False:
            while not model._stop:
                if pre_steps < 2:  # Frames iterates twice before starting plot
                    pre_steps += 1
                else:
                    model.run_step()
                    model.create_output()
                yield model.t
        else:  # Yield current if model stops before the animation starts
            yield model.t

    def update(t, m, axs, *fargs):  # noqa
        nonlocal pre_steps
        for ax in make_list(axs):
            # Clear axes before each plot
            ax.clear()
        plot(m, axs, *fargs)  # Perform plot

    ani = matplotlib.animation.FuncAnimation(
        fig, update,
        frames=frames,
        fargs=(model, axs, *fargs),
        save_count=model._steps,
        **kwargs)  # noqa

    plt.close()  # Don't display static plot
    return ani


def _apply_colors(grid, color_dict, convert):
    if isinstance(grid[0], list):
        return [_apply_colors(subgrid, color_dict, convert)
                for subgrid in grid]
    else:
        if color_dict is not None:
            grid = [i if i is np.nan else color_dict[i] for i in grid]
        if convert is True:
            grid = [(0., 0., 0., 0.) if i is np.nan else
                    matplotlib.colors.to_rgba(i) for i in grid]
        return grid


def gridplot(grid, color_dict=None, convert=False, ax=None, **kwargs):
    """ Visualizes values on a two-dimensional grid with
    :func:`matplotlib.pyplot.imshow`.

    Arguments:
        grid(list of list): Two-dimensional grid with values.
            numpy.nan values will be plotted as empty patches.
        color_dict(dict, optional): Dictionary that translates
            each value in `grid` to a color specification.
        convert(bool, optional): Convert values to rgba vectors,
             using :func:`matplotlib.colors.to_rgba` (default False).
        ax(matplotlib.pyplot.axis, optional): Axis to be used for plot.
        **kwargs: Forwarded to :func:`matplotlib.pyplot.imshow`.
     """

    # TODO Make feature for legend
    if color_dict is not None or convert:
        grid = _apply_colors(grid, color_dict, convert)
    if ax:
        ax.imshow(grid, **kwargs)
    else:
        plt.imshow(grid, **kwargs)
