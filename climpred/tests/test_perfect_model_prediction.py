import pytest

from climpred.bootstrap import bootstrap_perfect_model
from climpred.constants import PM_METRICS
from climpred.prediction import compute_perfect_model, compute_persistence
from climpred.tutorial import load_dataset

PM_COMPARISONS = {'m2c': '', 'e2c': ''}


@pytest.fixture
def pm_da_ds1d():
    da = load_dataset('MPI-PM-DP-1D')
    da = da['tos'].isel(area=1, period=-1)
    return da


@pytest.fixture
def pm_da_ds1d_lead0():
    da = load_dataset('MPI-PM-DP-1D')
    da = da['tos'].isel(area=1, period=-1)
    # Convert to lead zero for testing
    da['lead'] -= 1
    da['init'] += 1
    return da


@pytest.fixture
def pm_da_control1d():
    da = load_dataset('MPI-control-1D')
    da = da['tos'].isel(area=1, period=-1)
    return da


@pytest.fixture
def pm_ds_ds1d():
    ds = load_dataset('MPI-PM-DP-1D').isel(area=1, period=-1)
    return ds


@pytest.fixture
def pm_ds_control1d():
    ds = load_dataset('MPI-control-1D').isel(area=1, period=-1)
    return ds


@pytest.mark.parametrize('metric', ('rmse', 'pearson_r'))
def test_pvalue_from_bootstrapping(pm_da_ds1d, pm_da_control1d, metric):
    """Test that pvalue of initialized ensemble first lead is close to 0."""
    sig = 95
    actual = (
        bootstrap_perfect_model(
            pm_da_ds1d,
            pm_da_control1d,
            metric=metric,
            bootstrap=20,
            comparison='e2c',
            sig=sig,
        )
        .sel(kind='uninit', results='p')
        .isel(lead=0)
    )
    assert actual < 2 * (1 - sig / 100)


@pytest.mark.parametrize('metric', PM_METRICS)
def test_compute_persistence_ds1d_not_nan(pm_ds_ds1d, pm_ds_control1d, metric):
    """
    Checks that there are no NaNs on persistence forecast of 1D time series.
    """
    actual = (
        compute_persistence(pm_ds_ds1d, pm_ds_control1d, metric=metric).isnull().any()
    )
    for var in actual.data_vars:
        assert not actual[var]


@pytest.mark.parametrize('metric', PM_METRICS)
def test_compute_persistence_lead0_lead1(
    pm_da_ds1d, pm_da_ds1d_lead0, pm_da_control1d, metric
):
    """
    Checks that persistence forecast results are identical for a lead 0 and lead 1 setup
    """
    res1 = compute_persistence(pm_da_ds1d, pm_da_control1d, metric=metric)
    res2 = compute_persistence(pm_da_ds1d_lead0, pm_da_control1d, metric=metric)
    assert (res1.values == res2.values).all()


@pytest.mark.parametrize('comparison', PM_COMPARISONS)
@pytest.mark.parametrize('metric', PM_METRICS)
def test_compute_perfect_model_da1d_not_nan(
    pm_da_ds1d, pm_da_control1d, comparison, metric
):
    """
    Checks that there are no NaNs on perfect model metrics of 1D time series.
    """
    actual = (
        compute_perfect_model(
            pm_da_ds1d, pm_da_control1d, comparison=comparison, metric=metric
        )
        .isnull()
        .any()
    )
    assert not actual


@pytest.mark.parametrize('comparison', PM_COMPARISONS)
@pytest.mark.parametrize('metric', PM_METRICS)
def test_compute_perfect_model_lead0_lead1(
    pm_da_ds1d, pm_da_ds1d_lead0, pm_da_control1d, comparison, metric
):
    """
    Checks that metric results are identical for a lead 0 and lead 1 setup.
    """
    res1 = compute_perfect_model(
        pm_da_ds1d, pm_da_control1d, comparison=comparison, metric=metric
    )
    res2 = compute_perfect_model(
        pm_da_ds1d_lead0, pm_da_control1d, comparison=comparison, metric=metric
    )
    assert (res1.values == res2.values).all()


@pytest.mark.parametrize('comparison', PM_COMPARISONS)
@pytest.mark.parametrize('metric', PM_METRICS)
def test_bootstrap_perfect_model_da1d_not_nan(
    pm_da_ds1d, pm_da_control1d, metric, comparison
):
    """
    Checks that there are no NaNs on bootstrap perfect_model of 1D da.
    """
    actual = bootstrap_perfect_model(
        pm_da_ds1d,
        pm_da_control1d,
        metric=metric,
        comparison=comparison,
        sig=50,
        bootstrap=2,
    )
    actual_init_skill = actual.sel(kind='init', results='skill').isnull().any()
    assert not actual_init_skill
    actual_uninit_p = actual.sel(kind='uninit', results='p').isnull().any()
    assert not actual_uninit_p


@pytest.mark.parametrize('comparison', PM_COMPARISONS)
@pytest.mark.parametrize('metric', PM_METRICS)
def test_bootstrap_perfect_model_ds1d_not_nan(
    pm_ds_ds1d, pm_ds_control1d, metric, comparison
):
    """
    Checks that there are no NaNs on bootstrap perfect_model of 1D ds.
    """
    actual = bootstrap_perfect_model(
        pm_ds_ds1d,
        pm_ds_control1d,
        metric=metric,
        comparison=comparison,
        sig=50,
        bootstrap=2,
    )
    for var in actual.data_vars:
        actual_init_skill = actual[var].sel(kind='init', results='skill').isnull().any()
        assert not actual_init_skill
    for var in actual.data_vars:
        actual_uninit_p = actual[var].sel(kind='uninit', results='p').isnull().any()
        assert not actual_uninit_p


@pytest.mark.parametrize('metric', ('AnomCorr', 'test', 'None'))
def test_compute_perfect_model_metric_keyerrors(pm_da_ds1d, pm_da_control1d, metric):
    """
    Checks that wrong metric names get caught.
    """
    with pytest.raises(KeyError) as excinfo:
        compute_perfect_model(
            pm_da_ds1d, pm_da_control1d, comparison='e2c', metric=metric
        )
    assert 'Specify metric from' in str(excinfo.value)


@pytest.mark.parametrize('comparison', ('ensemblemean', 'test', 'None'))
def test_compute_perfect_model_comparison_keyerrors(
    pm_da_ds1d, pm_da_control1d, comparison
):
    """
    Checks that wrong comparison names get caught.
    """
    with pytest.raises(KeyError) as excinfo:
        compute_perfect_model(
            pm_da_ds1d, pm_da_control1d, comparison=comparison, metric='mse'
        )
    assert 'Specify comparison from' in str(excinfo.value)
