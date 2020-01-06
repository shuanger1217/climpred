import datetime
import warnings

import cftime
import numpy as np
import pandas as pd
import xarray as xr

from . import comparisons, metrics
from .checks import is_in_list
from .constants import METRIC_ALIASES


def convert_time_index(xobj, time_string, kind):
    """Converts incoming time index to a standard xr.CFTimeIndex.

    Args:
        xobj (xarray object): Dataset or DataArray with a time dimension to convert.
        time_string (str): Name of time dimension.
        kind (str): Kind of object for error message.

    Returns:
        Dataset or DataArray with converted time dimension. If incoming time index is
        ``xr.CFTimeIndex``, returns the same index. If ``pd.DatetimeIndex``, converts to
        ``cftime.ProlepticGregorian``. If ``pd.Int64Index`` or ``pd.Float64Index``,
        assumes annual resolution and returns year-start ``cftime.ProlepticGregorian``.

    Raises:
        ValueError: If ``time_index`` is not an ``xr.CFTimeIndex``, ``pd.Int64Index``,
            ``pd.Float64Index``, or ``pd.DatetimeIndex``.
    """
    xobj = xobj.copy()  # Ensures that main object index is not overwritten.
    time_index = xobj[time_string].to_index()

    if not isinstance(time_index, xr.CFTimeIndex):

        if isinstance(time_index, pd.DatetimeIndex):
            # Extract year, month, day strings from datetime.
            time_strings = [str(t) for t in time_index]
            split_dates = [d.split(' ')[0].split('-') for d in time_strings]

        # If Float64Index or Int64Index, assume annual and convert accordingly.
        elif isinstance(time_index, pd.Float64Index) | isinstance(
            time_index, pd.Int64Index
        ):
            warnings.warn(
                'Assuming annual resolution due to numeric inits. '
                'Change init to a datetime if it is another resolution.'
            )
            # TODO: What about decimal time? E.g. someone has 1955.5 or something?
            dates = [str(int(t)) + '-01-01' for t in time_index]
            split_dates = [d.split('-') for d in dates]

        else:
            raise ValueError(
                f'Your {kind} object must be pd.Float64Index, '
                'pd.Int64Index, xr.CFTimeIndex or '
                'pd.DatetimeIndex.'
            )
        # TODO: Account for differing calendars. Currently assuming `Gregorian`.
        cftime_dates = [
            cftime.DatetimeProlepticGregorian(int(y), int(m), int(d))
            for (y, m, d) in split_dates
        ]
        time_index = xr.CFTimeIndex(cftime_dates)
        xobj[time_string] = time_index

    return xobj


def get_metric_class(metric, list_):
    """
    This allows the user to submit a string representing the desired metric
    to the corresponding metric class.

    Currently compatable with functions:
    * compute_persistence()
    * compute_perfect_model()
    * compute_hindcast()

    Args:
        metric (str): name of metric.
        list_ (list): check whether metric in list

    Returns:
        metric (Metric): class object of the metric.
    """
    if isinstance(metric, metrics.Metric):
        return metric
    elif isinstance(metric, str):
        # check if metric allowed
        is_in_list(metric, list_, 'metric')
        metric = METRIC_ALIASES.get(metric, metric)
        return getattr(metrics, '__' + metric)
    else:
        raise ValueError(
            f'Please provide metric as str or Metric class, found {type(metric)}'
        )


def get_comparison_class(comparison, list_):
    """
    Converts a string comparison entry from the user into a Comparison class
     for the package to interpret.

    PERFECT MODEL:
    m2m: Compare all members to all other members.
    m2c: Compare all members to the control.
    m2e: Compare all members to the ensemble mean.
    e2c: Compare the ensemble mean to the control.

    HINDCAST:
    e2r: Compare the ensemble mean to the reference.
    m2r: Compare each ensemble member to the reference.

    Args:
        comparison (str): name of comparison.

    Returns:
        comparison (Comparison): comparison class.

    """
    if isinstance(comparison, comparisons.Comparison):
        return comparison
    else:
        is_in_list(comparison, list_, 'comparison')
        return getattr(comparisons, '__' + comparison)


def get_lead_cftime_shift_args(units, lead):
    """Determines the date increment to use when adding the lead time to init time based
    on the units attribute.

    Args:
        units (str): Units associated with the lead dimension. Must be
            years, seasons, months, weeks, pentads, days.
        lead (int): increment of lead being computed.

    Returns:
       offset_args_tuple (tuple): Tuple containing (value, str) for ``CFTime.shift()``.
    """
    lead = int(lead)
    if units == 'years':
        # Currently assumes yearly aligns with year start.
        offset_args_tuple = (lead, 'YS')
    elif units == 'months':
        # Currently assume monthly aligns with month start.
        offset_args_tuple = (lead, 'MS')
    elif units == 'weeks':
        offset_args_tuple = (lead * 7, 'D')
    elif units == 'days':
        offset_args_tuple = (lead, 'D')
    elif units == 'seasons':
        offset_args_tuple = (lead * 3, 'MS')
    elif units == 'pentads':
        offset_args_tuple = (lead * 5, 'D')
    else:
        raise ValueError(f'{units} is not a valid choice')
    return offset_args_tuple


def intersect(lst1, lst2):
    """
    Custom intersection, since `set.intersection()` changes type of list.
    """
    lst3 = [value for value in lst1 if value in lst2]
    return np.array(lst3)


def reduce_time_series(forecast, reference, nlags):
    """Reduces forecast and reference to common time frame for prediction and lag.

    Args:
        forecast (`xarray` object): prediction ensemble with inits.
        reference (`xarray` object): reference being compared to (for skill,
                                     persistence, etc.)
        nlags (int): number of lags being computed

    Returns:
       forecast (`xarray` object): prediction ensemble reduced to
       reference (`xarray` object):
    """
    time_index = reference['time'].to_index()
    offset_args_tuple = get_lead_cftime_shift_args(
        getattr(forecast['lead'], 'units'), nlags
    )
    shift_n = offset_args_tuple[0] * -1
    shift_str = offset_args_tuple[1]
    ref_dates = time_index.shift(shift_n, shift_str)

    imin = max(forecast.time.min(), reference.time.min())
    imax = min(forecast.time.max(), ref_dates.max())
    imax = xr.DataArray(imax).rename('time')
    forecast = forecast.where(forecast.time <= imax, drop=True)
    forecast = forecast.where(forecast.time >= imin, drop=True)
    reference = reference.where(reference.time >= imin, drop=True)
    return forecast, reference


def assign_attrs(
    skill,
    ds,
    function_name,
    metadata_dict=None,
    metric=None,
    comparison=None,
    dim=None,
):
    """Write information about prediction skill into attrs.

    Args:
        skill (`xarray` object): prediction skill.
        ds (`xarray` object): prediction ensemble with inits.
        function_name (str): name of compute function
        metadata_dict (dict): optional attrs
        metric (class) : metric used in comparing the forecast and reference.
        comparison (class): how to compare the forecast and reference.
        dim (str): Dimension over which metric was applied.

    Returns:
       skill (`xarray` object): prediction skill with additional attrs.
    """
    # assign old attrs
    skill.attrs = ds.attrs

    # climpred info
    skill.attrs[
        'prediction_skill'
    ] = f'calculated by climpred https://climpred.readthedocs.io/'
    skill.attrs['skill_calculated_by_function'] = function_name
    if 'init' in ds.coords:
        skill.attrs['number_of_initializations'] = ds.init.size
    if 'member' in ds.coords:
        skill.attrs['number_of_members'] = ds.member.size

    skill.attrs['metric'] = metric.name
    skill.attrs['comparison'] = comparison.name
    skill.attrs['dim'] = dim

    # change unit power
    if metric.unit_power == 0:
        skill.attrs['units'] = 'None'
    if metric.unit_power >= 2 and 'units' in skill.attrs:
        p = metric.unit_power
        p = int(p) if int(p) == p else p
        skill.attrs['units'] = f"({skill.attrs['units']})^{p}"

    # check for none attrs and remove
    del_list = []
    for key, value in metadata_dict.items():
        if value is None and key != 'units':
            del_list.append(key)
    for entry in del_list:
        del metadata_dict[entry]

    # write optional information
    if metadata_dict is None:
        metadata_dict = dict()
    skill.attrs.update(metadata_dict)

    skill.attrs[
        'created'
    ] = f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S%f")[:-6]}'
    return skill


def copy_coords_from_to(xro_from, xro_to):
    """Copy coords from one xr object to another."""
    if isinstance(xro_from, xr.DataArray) and isinstance(xro_to, xr.DataArray):
        for c in xro_from.coords:
            xro_to[c] = xro_from[c]
        return xro_to
    elif isinstance(xro_from, xr.Dataset) and isinstance(xro_to, xr.Dataset):
        xro_to = xro_to.assign_coords(**xro_from.coords)
    else:
        raise ValueError(
            f'xro_from and xro_to must be both either xr.DataArray or',
            f'xr.Dataset, found {type(xro_from)} {type(xro_to)}.',
        )
    return xro_to
