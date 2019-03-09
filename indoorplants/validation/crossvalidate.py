import collections
from itertools import chain
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold, KFold
from sklearn.metrics import confusion_matrix


def train_and_score(model_obj, score_funcs, X_train, y_train,
                     X_test, y_test, train_scores=True):
    """
    Trains model to training data, outputs score(test data) 
    for each score in 'score_funcs', and does the same for 
    train data unless 'train_data' is set to False
    """
    model = model_obj.fit(X_train, y_train)

    y_hat_train = model.predict(X_train)
    y_hat_test = model.predict(X_test)

    apply_score_func = lambda func: (
                            func(y_train, y_hat_train), func(y_test, y_hat_test)
                                          ) if train_scores is True else
                            func(y_test, y_hat_test) 

    return list(map(apply_score_func, score_funcs))


def cv_engine(X, y, model_obj, score_funcs, splits=5,
              scale_obj=None, train_scores=True, random_state=0):
    """
    Splits data (based on whether model is classifier
    or regressor) and passes each fold to the train_and_score
    function.

    Collects results and returns results as List.
    """
    if model_obj._estimator_type == 'classifier':
        skf = StratifiedKFold(n_splits=splits, random_state=random_state)

    elif model_obj._estimator_type == 'regressor':
        skf = KFold(n_splits=splits, suffle=True, random_state=random_state)

    else:
        raise TypeError('Improper model type.')

    results = []
    for train, test in skf.split(X, y):
        y_train = y.iloc[train]
        y_test = y.iloc[test]

        X_train = X.iloc[train, :]
        X_test = X.iloc[test, :]

        if scale_obj is not None:
            X_train = scale_obj.fit_transform(X_train)
            X_test = scale_obj.fit_transform(X_test)

        results.append(
            train_and_score(
                model_obj, score_funcs, X_train, y_train, X_test, y_test, train_scores
                ))

    return results


def format_cv_results(results, score_funcs, train_scores=True):
    """
    Takes results from cv_engine and returns as 
    unaggregated DataFrame, where trial number & score 
    function used are represented in index.
    """
    if train_scores is False:
        cols = [score.__name__ for score in score_funcs]
        return pd.DataFrame(res, columns=cols)

    else:
        res = np.array([tuple(chain(*trial)) for trial in results]) # do I like 'trial'?
        dfs = []

        for i in range(0, res.shape[1], 2):
            dfs.append(
                pd.concat(
                    {
                    score_funcs[i // 2].__name__: 
                        pd.DataFrame(res[:, i:i+2], columns=['train', 'test'])
                        },
                    axis=1
                    ))

        return dfs[0].join(dfs[1:])


def describe_dataframe(results, stats_to_run=["mean", "std"]):
    """
    Given DF of CV results, returns DF of descriptive statistics.

    parameters
    ----------

    results: pandas.DataFrame
        CV results, upon upon which descriptive statistics are to be run.

    stats_to_run: str or list-like of str
        pandas.DataFrame method name(s) indicating statistic to be run,
        e.g. "mean" or ["mean", "std"]

    return
    ------

    pandas.DataFrame of descriptive statistics, where rows correspond to
    columns of `results` and where each columns correspond to `stats_to_run`.

    """
    if isinstance(stats_to_run, str):
        stats_to_run = [stats_to_run]

    get_stats = lambda func_name: getattr(results, func_name)(
                                         ).rename(func_name
                                         ).to_frame()

    to_return = [get_stats(s) for s in stats_to_run]

    return to_return[0].join(to_return[1:])


def cv_score(X, y, model_obj, score_funcs, splits=5,
             scale_obj=None, train_scores=True,
             stats_to_run=["mean", "std"]):
    """
    Cross-validates passed model and returns performance statistics. Cross-validiation
    is performed using shuffling. If passed model is a classifier, shuffling is performed
    such that existing stratification of classes is preserved.

    parameters
    ----------

    X: pd.DataFrame
        Exogenous variables to be used as model inputs.

    y: pd.Series
        Endogenous variable that should be predicted by the model.

    model_obj: sklearn.BaseEstimator
        Instantiated (i.e. this is an instance of a class to which hyper-parameters
        have already been passed) scikit-learn model, or model with similar API - i.e.
        `model_obj.fit(X, y)` and `model_obj.predict(X)` would be used for model fitting
        and predicting, respectively. E.g. `sklearn.RandomForestClassifier(max_depth=16)`.

    score_funcs: callable, or list-like of callables
        Score function(s) to be run on model predictions. E.g. `sklearn.metrics.accuracy_score`
        or `[sklearn.metrics.f1_score, sklearn.metrics.accuracy_score]`.

    splits: int, optional(default=5)
        Number of splits to use for k-fold cross-validation.

    scale_obj: sklearn.TransformerMixin, optional(default=None)
        Should be a scikit-learn transform object (i.e. inherits from sklearn.BaseEstimator
        and sklearn.TransformerMixin) or have a similar API (i.e. `scale_obj.fit_transform()`
        works as expected). If passed, X will be scaled within each fold so as to prevent data
        leakage. 

    train_scores: bool, optional(default=True)
        Determines whether training scores, in addition to test scores, are returned. Train
        scores are useful for comparing to test scores in order to assess model fit.

    stats_to_run: str or list-like of str, optional(default=["mean", "std"])
        pandas.DataFrame method name(s) indicating statistic to be run,
        e.g. "mean" or `["mad", "var"]`.

    return
    ------

    pandas.DataFrame of descriptive statistics, as specified in `describe_dataframe`.
    """
    if callable(score_funcs):
        score_funcs = [score_funcs]

    return describe_dataframe(
                format_cv_results(
                    cv_engine(
                        X, y, model_obj, score_funcs, splits, scale_obj, train_scores
                        ), 
                    score_funcs, train_scores))


def cv_conf_mat(X, y, model_obj, splits=5, scale_obj=None):
    """
    Return confusion matrix for each CV trial.
    """
    results = cv_engine(X=X, y=y, model_obj=model_obj, 
                        score_funcs=confusion_matrix, 
                        splits=splits, scale_obj=scale_obj, 
                        train_scores=False)

    results = [pd.concat(
                {
                    i: pd.DataFrame(trial[0],
                                    index=['neg_true', 'pos_true'],
                                    columns=['neg_pred', 'pos_pred'])
                }
               ) for i, trial in enumerate(results, 1)]

    return pd.concat(results)


def validate_param_range(X, y, model_type, param_name, param_range,
                         score_funcs, other_params={}, splits=5,
                         scale_obj=None, train_scores=True):
    """
    Returns validation.cv_score across values in `param_range`
    for `param_name`, which should be a working parameter for the
    passed model.

    `model_type` should be an uninstantiated sklearn model (or
    one with similar fit and predict methods). Additional 
    hyper-parameters (i.e. not `param_name` should be passed
    in to `other_params` as dictionary.

    Please see validation.cv_score for details on other args.
    """ 
    results = {}
    for val in param_range:
        model_obj = model_type(**{param_name: val}, **other_params)

        some_kwargs = {'model_obj': model_obj, 'X': X, 'y': y, 
                       'splits': splits, 'scale_obj': scale_obj}

        other_kwargs = {'train_scores': train_scores, 'score_funcs': score_funcs}

        if isinstance(val, collections.Iterable):
            val = str(val) # how to sort this?

        res = cv_engine(**some_kwargs, **other_kwargs)
        results[val] = format_cv_results(res, **other_kwargs)

    return pd.concat(results)


def validate_param_range(X, y, model_type, param_name, param_range,
                         score_funcs, other_params={}, splits=5,
                         scale_obj=None, train_scores=True):
    """
    Returns validation.cv_score across values in 'param_range'
    for 'param_name', which should be a working parameter for the
    passed model.

    'model_type' should be an uninstantiated sklearn model (or
    one with similar fit and predict methods). Additional 
    hyper-parameters (i.e. not 'param_name' should be passed
    in to 'other_params' as dictionary.

    Please see validation.cv_score for details on other args.
    """ 
    results = {}
    for val in param_range:
        model_obj = model_type(**{param_name: val}, **other_params)

        some_kwargs = {'model_obj': model_obj, 'X': X, 'y': y, 
                       'splits': splits, 'scale_obj': scale_obj}

        other_kwargs = {'train_scores': train_scores, 'score_funcs': score_funcs}

        if isinstance(val, collections.Iterable):
            val = str(val) # how to sort this?

        res = cv_engine(**some_kwargs, **other_kwargs)
        results[val] = format_cv_results(res, **other_kwargs)

    return pd.concat(results)