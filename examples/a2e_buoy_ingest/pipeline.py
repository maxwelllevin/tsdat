import os
import re
import cmocean
import numpy as np
import pandas as pd
import xarray as xr
import seaborn as sns
import matplotlib as mpl
import matplotlib.pyplot as plt

from typing import Any, Dict, List
from tsdat.config import VariableDefinition, DatasetDefinition
from tsdat.pipeline import IngestPipeline
from tsdat.utils import DSUtil

example_dir = os.path.abspath(os.path.dirname(__file__))
style_file = os.path.join(example_dir, "styling.mplstyle")
plt.style.use(style_file)

class BuoyIngestPipeline(IngestPipeline):
    """-------------------------------------------------------------------
    This is an example class that extends the default IngestPipeline in
    order to hook in custom behavior such as creating custom plots.
    If users need to apply custom changes to the dataset, instrument
    corrections, or create custom plots, they should follow this example
    to extend the IngestPipeline class.
    -------------------------------------------------------------------"""
    def customize_raw_datasets(self, raw_dataset_mapping: Dict[str, xr.Dataset]) -> Dict[str, xr.Dataset]:
        """-------------------------------------------------------------------
        Hook to allow for user customizations to one or more raw xarray Datasets
        before they merged and used to create the standardized dataset.  The
        raw_dataset_mapping will contain one entry for each file being used
        as input to the pipeline.  The keys are the standardized raw file name,
        and the values are the datasets.

        This method would typically only be used if the user is combining
        multiple files into a single dataset.  In this case, this method may
        be used to correct coordinates if they don't match for all the files,
        or to change variable (column) names if two files have the same
        name for a variable, but they are two distinct variables.

        This method can also be used to check for unique conditions in the raw
        data that should cause a pipeline failure if they are not met.

        This method is called before the inputs are merged and converted to
        standard format as specified by the config file.

        Args:
            raw_dataset_mapping (Dict[str, xr.Dataset])     The raw datasets to
                                                            customize.

        Returns:
            Dict[str, xr.Dataset]: The customized raw dataset.
        -------------------------------------------------------------------"""
        dod = self.config.dataset_definition
        time_def = dod.get_variable("time")
        
        for filename, dataset in raw_dataset_mapping.items():
            if "surfacetemp" in filename: 
                old_name = "Surface Temperature (C)"
                new_name = "surfacetemp - Surface Temperature (C)"
                raw_dataset_mapping[filename] = dataset.rename_vars({old_name: new_name})

            if "gill" in filename:
                name_mapping = {
                    "Horizontal Speed (m/s)":       "gill_horizontal_wind_speed",
                    "Horizontal Direction (deg)":   "gill_horizontal_wind_direction" 
                }
                raw_dataset_mapping[filename] = dataset.rename_vars(name_mapping)
            
            if "currents" in filename:
               
                def has_vel_and_dir(index: int) -> bool:
                    has_vel = f"Vel{index+1} (mm/s)" in dataset.variables
                    has_dir = f"Dir{index+1} (deg)" in dataset.variables
                    return has_vel and has_dir

                # Calculate depths and collect data vars
                i = 0
                depth, vel_data, dir_data = [], [], []
                while has_vel_and_dir(i):
                    depth.append(4 * (i + 1))
                    vel_data.append(dataset[f"Vel{i+1} (mm/s)"].data)
                    dir_data.append(dataset[f"Dir{i+1} (deg)"].data)
                    i += 1

                depth = np.array(depth)
                vel_data = np.array(vel_data).transpose()
                dir_data = np.array(dir_data).transpose()

                # Make time.input.name and depth coordinate variables
                dataset = dataset.set_coords(time_def.get_input_name())
                dataset["depth"] = xr.DataArray(data=depth, dims=["depth"])
                dataset = dataset.set_coords("depth")

                # Add current velocity and direction data to dataset
                dataset["current_velocity"] = xr.DataArray(data=vel_data, dims=["time", "depth"])
                dataset["current_direction"] = xr.DataArray(data=dir_data, dims=["time", "depth"])

                raw_dataset_mapping[filename] = dataset

        # No customization to raw data - return original dataset
        return raw_dataset_mapping
    
    def create_and_persist_plots(self, dataset: xr.Dataset) -> None:
        """-------------------------------------------------------------------
        Hook to allow users to create plots from the xarray dataset after
        processing and QC have been applied and just before the dataset is
        saved to disk.

        To save on filesystem space (which is limited when running on the
        cloud via a lambda function), this method should only
        write one plot to local storage at a time. An example of how this
        could be done is below:

        ```
        filename = DSUtil.get_plot_filename(dataset, "sea_level", "png")
        with self.storage._tmp.get_temp_filepath(filename) as tmp_path:
            fig, ax = plt.subplots(figsize=(10,5))
            ax.plot(dataset["time"].data, dataset["sea_level"].data)
            fig.save(tmp_path)
            storage.save(tmp_path)

        filename = DSUtil.get_plot_filename(dataset, "qc_sea_level", "png")
        with self.storage._tmp.get_temp_filepath(filename) as tmp_path:
            fig, ax = plt.subplots(figsize=(10,5))
            DSUtil.plot_qc(dataset, "sea_level", tmp_path)
            storage.save(tmp_path)
        ```

        Args:
            dataset (xr.Dataset):   The xarray dataset with customizations and
                                    QC applied.
        -------------------------------------------------------------------"""

        def format_time_xticks(ax, /, *, start=4, stop=21, step=4, date_format="%H-%M"):
            ax.xaxis.set_major_locator(mpl.dates.HourLocator(byhour=range(start, stop, step)))
            ax.xaxis.set_major_formatter(mpl.dates.DateFormatter(date_format))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=0)

        def add_colorbar(ax, plot, label):
            cb = plt.colorbar(plot, ax=ax, pad=0.01)
            cb.ax.set_ylabel(label, fontsize=12)
            cb.outline.set_linewidth(1)
            cb.ax.tick_params(size=0)
            cb.ax.minorticks_off()
            return cb
        
        def double_plot(ax, twin, /, *, data, colors, var_labels=["",""], ax_labels=["",""], **kwargs):
            def _add_lineplot(_ax, _data, _c, _label, _ax_label, _spine):
                _line = _data.plot(ax=_ax, c=_c, label=_label, linewidth=2, **kwargs)
                _ax.tick_params(axis="y", which="both", colors=_c)
                _ax.set_ylabel(_ax_label, color=_c)
                _ax.spines[_spine].set_color(_c)
            _add_lineplot(ax, data[0], colors[0], var_labels[0], ax_labels[0], "left")
            _add_lineplot(twin, data[1], colors[1], var_labels[1], ax_labels[1], "right")
            twin.spines["left"].set_color(colors[0])  # twin overwrites ax, so set color here
            lines = ax.lines + twin.lines
            labels = [line.get_label() for line in lines]
            twin.legend(lines, labels, ncol=len(labels), loc=1)

        # Useful variables
        ds = dataset
        date = pd.to_datetime(ds.time.data[0]).strftime('%d-%b-%Y')
        cmap = sns.color_palette("viridis", as_cmap=True)
        colors = [cmap(0.00), cmap(0.60)]

        # Create the first plot -- Surface Met Parameters
        filename = DSUtil.get_plot_filename(dataset, "surface_met_parameters", "png")
        with self.storage._tmp.get_temp_filepath(filename) as tmp_path:

            # Define data and metadata
            data = [
                [ds.wind_speed, ds.wind_direction], 
                [ds.pressure, ds.rh], 
                [ds.air_temperature, ds.CTD_SST]]
            var_labels = [
                [r"$\overline{\mathrm{U}}$ Cup", r"$\overline{\mathrm{\theta}}$ Cup"],
                ["Pressure", "Relative Humidity"],
                ["Air Temperature", "Sea Surface Temperature"]]
            ax_labels = [
                [r"$\overline{\mathrm{U}}$ (ms$^{-1}$)", r"$\bar{\mathrm{\theta}}$ (degrees)"],
                [r"$\overline{\mathrm{P}}$ (bar)", r"$\overline{\mathrm{RH}}$ (%)"],
                [r"$\overline{\mathrm{T}}_{air}$ ($\degree$C)", r"$\overline{\mathrm{SST}}$ ($\degree$C)"]]

            # Create figure and axes objects
            fig, axs = plt.subplots(nrows=3, figsize=(14, 8), constrained_layout=True)
            twins = [ax.twinx() for ax in axs]
            fig.suptitle(f"Surface Met Parameters at {ds.attrs['location_meaning']} on {date}")

            # Create the plots
            gill_data = [ds.gill_wind_speed, ds.gill_wind_direction]
            gill_labels = [r"$\overline{\mathrm{U}}$ Gill", r"$\overline{\mathrm{\theta}}$ Gill"]
            double_plot(axs[0], twins[0], data=gill_data, colors=colors, var_labels=gill_labels, linestyle="--")
            for i in range(3):
                double_plot(axs[i], twins[i], data=data[i], colors=colors, var_labels=var_labels[i], ax_labels=ax_labels[i])
                axs[i].grid(which="both", color='lightgray', linewidth=0.5)
                format_time_xticks(axs[i])
            
            # Save and close the figure
            fig.savefig(tmp_path, dpi=100)
            self.storage.save(tmp_path)
            plt.close()

        # Create the second plot -- Conductivity and Sea Surface Temperature
        filename = DSUtil.get_plot_filename(dataset, "conductivity", "png")
        with self.storage._tmp.get_temp_filepath(filename) as tmp_path:
            data = [ds.conductivity, ds.CTD_SST]
            var_labels = [r"Conductivity (S m$^{-1}$)", r"$\overline{\mathrm{SST}}$ ($\degree$C)"]
            ax_labels = [r"Conductivity (S m$^{-1}$)", r"$\overline{\mathrm{SST}}$ ($\degree$C)"]

            fig, ax = plt.subplots(figsize=(14, 8), constrained_layout=True)
            fig.suptitle(f"Conductivity and Sea Surface Temperature at {ds.attrs['location_meaning']} on {date}")

            double_plot(ax, ax.twinx(), data=data, colors=colors, var_labels=var_labels, ax_labels=ax_labels)
            ax.grid(which="both", color='lightgray', linewidth=0.5)
            format_time_xticks(ax)

            # Save and close the figure
            fig.savefig(tmp_path, dpi=100)
            self.storage.save(tmp_path)
            plt.close()

        # Create third plot -- current direction and velocity
        filename = DSUtil.get_plot_filename(dataset, "currents", "png")
        with self.storage._tmp.get_temp_filepath(filename) as tmp_path:
            ds: xr.Dataset = dataset.resample(time="1H").mean(keep_attrs=True)
            ds: xr.Dataset = ds.coarsen(depth=2, keep_attrs=True).mean(keep_attrs=True)

            # Calculations for contour plots
            date = pd.to_datetime(ds.time.data[0]).strftime('%d-%b-%Y')
            hi = np.ceil(ds.current_velocity.max().data + 1)
            lo = np.floor(ds.current_velocity.min().data)
            levels = 30

            # Calculations for quiver plot
            qv_degrees = ds.current_direction.data.transpose()
            qv_theta = (qv_degrees + 90) * (np.pi/180)
            X, Y = ds.time.data, ds.depth.data
            U, V = np.cos(-qv_theta), np.sin(-qv_theta)

            # Create figure and axes objects
            fig, ax = plt.subplots(figsize=(16,8), constrained_layout=True)
            fig.suptitle(f"Average current speed and direction at {ds.attrs['location_meaning']} on {date}")

            # Make top subplot -- contours and quiver plots for wind speed and direction
            csf = ds.current_velocity.plot.contourf(ax=ax, x="time", yincrease=False, levels=levels, cmap=cmocean.cm.deep_r, add_colorbar=False)
            ds.current_velocity.plot.contour(ax=ax, x="time", yincrease=False, levels=levels, colors="lightgray", linewidths=0.5)
            ax.quiver(X, Y, U, V, width=0.002, scale=60, color="white", zorder=10, label="Current Direction (degrees)")
            cb = add_colorbar(ax, csf, r"Current Speed (mm s$^{-1}$)")
            format_time_xticks(ax)
            ax.set_ylabel("Depth (m)")

            # Save the figure
            fig.savefig(tmp_path, dpi=100)
            self.storage.save(tmp_path)
            plt.close()
        return
