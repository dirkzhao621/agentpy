"""
Agentpy Experiment Module
Content: Experiment class
"""

import pandas as pd
import ipywidgets
import IPython

from datetime import datetime, timedelta
from .tools import make_list
from .output import DataDict


class Experiment:
    """ Experiment for an agent-based model.
    Allows for multiple iterations, parameter samples, distict scenarios,
    interactive output, and parallel processing.

    Arguments:
        model_class(class): The model class type that the experiment should use.
        parameters(dict or list of dict, optional): Parameter dictionary
            or sample (list of parameter dictionaries) (default None).
        name(str, optional): Name of the experiment (default model.name).
        scenarios(str or list, optional): Experiment scenarios (default None).
        iterations(int, optional): Experiment repetitions (default 1).
        record(bool, optional): Record dynamic variables (default False).

    Attributes:
        output(DataDict): Recorded experiment data
    """  # TODO Repeat arguments in attribute list? / Type hint for model?

    def __init__(self, model_class, parameters=None, name=None, scenarios=None,
                 iterations=1, record=False):

        self.model = model_class
        self.output = DataDict()
        self.iterations = iterations
        self.record = record

        if name:
            self.name = name
        else:
            self.name = model_class.__name__

        # Transform input into iterable lists if only a single value is given
        # keep_none assures that make_list(None) returns iterable [None]
        self.scenarios = make_list(scenarios, keep_none=True)
        self.parameters = make_list(parameters, keep_none=True)
        self._parameters_to_output()  # Record parameters

        # Log
        self.output.log = {'name': self.name,
                           'time_stamp': str(datetime.now()),
                           'iterations': iterations}
        if scenarios:
            self.output.log['scenarios'] = scenarios

        # Prepare runs
        self.parameters_per_run = self.parameters * self.iterations
        self.number_of_runs = len(self.parameters_per_run)

    def _parameters_to_output(self):
        """ Document parameters (seperately for fixed & variable) """
        df = pd.DataFrame(self.parameters)
        df.index.rename('sample_id', inplace=True)
        fixed_pars = {}
        for col in df.columns:
            s = df[col]
            # TODO Error if parameters are unhashable (e.g. dict) (not list?)
            if len(s.unique()) == 1:
                fixed_pars[s.name] = df[col][0]
                df.drop(col, inplace=True, axis=1)
        if fixed_pars and df.empty:
            self.output['parameters'] = fixed_pars
        elif not fixed_pars and not df.empty:
            self.output['parameters'] = df
        else:
            self.output['parameters'] = DataDict({
                'fixed': fixed_pars,
                'varied': df
            })

    def interactive(self, plot, *args, **kwargs):
        """
        Displays interactive output for Jupyter notebooks,
        using :mod:`IPython` and :mod:`ipywidgets`.
        A slider will be shown for all varied parameters,
        and the output from 'plot' will be refreshed
        every time a parameter value is changed.

        Arguments:
            plot: Function that takes a model instance as input
                and prints or plots the desired output..
            *args: Will be forwarded to 'plot'.
            **kwargs: Will be forwarded to 'plot'.

        Returns:
            ipywidgets.HBox: Interactive output widget
        """

        # TODO Pass settings to widget

        def var_run(**param_updates):

            IPython.display.clear_output()
            parameters = dict(self.parameters[0])
            parameters.update(param_updates)
            temp_model = self.model(parameters)
            temp_model.run()
            IPython.display.clear_output()
            plot(temp_model, *args, **kwargs)

        # Get variable parameters
        if 'varied' in self.output['parameters']:
            var_pars = self.output['parameters']['varied']
        elif isinstance(self.output['parameters'], pd.DataFrame):
            var_pars = self.output['parameters']
        else:
            raise AgentpyError("No varied parameters found.")

        # Create widget dict
        widget_dict = {}
        for par_key in list(var_pars):
            par_list = list(var_pars[par_key])

            widget_dict[par_key] = ipywidgets.SelectionSlider(
                options=par_list,
                value=par_list[0],
                description=par_key,
                continuous_update=False,
                style=dict(description_width='initial'),
                layout={'width': '300px'}
            )

        widgets_left = ipywidgets.VBox(list(widget_dict.values()))
        output_right = ipywidgets.interactive_output(var_run, widget_dict)

        return ipywidgets.HBox([widgets_left, output_right])

    def _add_single_output_to_combined(self, single_output, combined_output):
        """Append results from single run to combined output."""
        for key, value in single_output.items():

            # Skip parameters & log
            if key in ['parameters', 'log']:
                continue

            # Skip variables if record is False
            if key == 'variables' and not self.record:
                continue

            # Handle variable subdicts
            if key == 'variables' and isinstance(value, DataDict):

                if key not in combined_output:
                    combined_output[key] = {}

                for obj_type, obj_df in single_output[key].items():

                    if obj_type not in combined_output[key]:
                        combined_output[key][obj_type] = []

                    combined_output[key][obj_type].append(obj_df)

            # Handle other output types
            else:
                if key not in combined_output:
                    combined_output[key] = []
                combined_output[key].append(value)

    def _combine_dataframes(self, combined_output):
        for key, values in combined_output.items():
            if values and all([isinstance(value, pd.DataFrame)
                               for value in values]):
                self.output[key] = pd.concat(values)
            elif isinstance(values, dict):  # Create SubDataDict
                self.output[key] = DataDict()
                for sk, sv in values.items():
                    self.output[key][sk] = pd.concat(sv)
            elif key != 'log':
                self.output[key] = values

    def _single_sim(self, sim_id):
        """ Perform a single simulation for parallel processing."""
        sc_id = sim_id % len(self.scenarios)
        run_id = (sim_id - sc_id) // len(self.scenarios)
        model = self.model(
            self.parameters[run_id],
            run_id=run_id,
            scenario=self.scenarios[sc_id])
        results = model.run(display=False)
        # TODO RESET FUNCTION
        # TODO SKIP FUNCTION
        return results

    def run(self, pool=None, display=True):
        """ Executes the simulation of the experiment.

        The simulation will run the model once for each set of parameters
        and will repeat this process for the set number of iterations.
        Parallel processing is possible if a `pool` is passed.
        Simulation results will be stored in `Experiment.output`.

        Arguments:
            pool(multiprocessing.Pool, optional):
                Pool of active processes for parallel processing.
                If none is passed, normal processing is used.
            display(bool, optional):
                Display simulation progress (default True).

        Returns:
            DataDict: Recorded experiment data.

        Examples:

            To run a normal experiment::

                exp = ap.Experiment(MyModel, parameters)
                results = exp.run()

            To use parallel processing::

                import multiprocessing as mp
                if __name__ ==  '__main__':
                    exp = ap.Experiment(MyModel, parameters)
                    pool = mp.Pool(mp.cpu_count())
                    results = exp.run(pool)
        """  # TODO Examples can be improved

        if display:
            print(f"Scheduled runs: {self.number_of_runs}")
        t0 = datetime.now()  # Time-Stamp Start
        combined_output = {}

        # Normal processing
        if pool is None:
            for i, parameters in enumerate(self.parameters_per_run):
                for scenario in self.scenarios:
                    # Run model for current parameters & scenario
                    output = self.model(
                        parameters, run_id=i,
                        scenario=scenario).run(display=False)
                    self._add_single_output_to_combined(output,
                                                        combined_output)

                if display:
                    td = (datetime.now() - t0).total_seconds()
                    te = timedelta(seconds=int(td / (i + 1)
                                               * (self.number_of_runs - i - 1)))
                    print(f"\rCompleted: {i + 1}, "
                          f"estimated time remaining: {te}", end='')
            if display:
                print("")  # Because the last print ended without a line-break

        # Parallel processing
        else:
            if display:
                print(f"Active processes: {pool._processes}")
            sim_ids = list(range(self.number_of_runs * len(self.scenarios)))
            output_list = pool.map(self._single_sim, sim_ids)
            # TODO dynamic variables take a lot of memory
            for single_output in output_list:
                self._add_single_output_to_combined(single_output, combined_output)

        self._combine_dataframes(combined_output)
        self.output.log['run_time'] = ct = str(datetime.now() - t0)

        if display:
            print(f"Experiment finished\nRun time: {ct}")

        return self.output
