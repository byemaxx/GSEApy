#! python
# -*- coding: utf-8 -*-

import os
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd

from gseapy.base import GSEAbase
from gseapy.gse import gsva_rs
from gseapy.utils import mkdirs


class GSVA(GSEAbase):
    """GSVA"""

    def __init__(
        self,
        data: Union[pd.DataFrame, pd.Series, str],
        gene_sets: Union[List[str], str, Dict[str, str]],
        outdir: Optional[str] = None,
        kcdf: Optional[str] = "Gaussian",
        weight: float = 1.0,
        mx_diff: bool = True,
        abs_rnk: bool = False,
        min_size: int = 15,
        max_size: int = 500,
        threads: int = 1,
        seed: int = 123,
        verbose: bool = False,
        **kwargs,
    ):
        super(GSVA, self).__init__(
            outdir=outdir,
            gene_sets=gene_sets,
            module="gsva",
            threads=threads,
            verbose=verbose,
        )
        self.data = data
        self.tau = weight
        self.min_size = min_size
        self.max_size = max_size
        self.seed = seed
        self.mx_diff = mx_diff
        self.abs_rnk = abs_rnk
        self.ranking = None
        self.permutation_num = 0
        self._noplot = True
        if kcdf in ["Gaussian", "gaussian"]:
            self.kernel = True
            self.rnaseq = False
        elif kcdf in ["Poisson", "poisson"]:
            self.kernel = True
            self.rnaseq = True
        else:
            self.kernel = False
            self.rnaseq = False

        # self.figsize = figsize
        # self.format = format
        # self.graph_num = int(graph_num)
        # self.seed = seed
        self.ranking = None
        self.permutation_type = "gene_set"

    def load_data(self) -> pd.DataFrame:
        # load data
        exprs = self.data
        if isinstance(exprs, pd.DataFrame):
            rank_metric = exprs.copy()
            # handle dataframe with gene_name as index.
            self._logger.debug("Input data is a DataFrame with gene names")
            # handle index is not gene_names
            if rank_metric.index.dtype != "O":
                rank_metric.set_index(keys=rank_metric.columns[0], inplace=True)
            if rank_metric.columns.dtype != "O":
                rank_metric.columns = rank_metric.columns.astype(str)

            rank_metric = rank_metric.select_dtypes(include=[np.number])
        elif isinstance(exprs, pd.Series):
            # change to DataFrame
            self._logger.debug("Input data is a Series with gene names")
            if exprs.name is None:
                # rename col if name attr is none
                exprs.name = "sample1"
            elif exprs.name.dtype != "O":
                exprs.name = exprs.name.astype(str)
            rank_metric = exprs.to_frame()
        elif os.path.isfile(exprs):
            # GCT input format?
            if exprs.endswith("gct"):
                rank_metric = pd.read_csv(
                    exprs, skiprows=1, comment="#", index_col=0, sep="\t"
                )
            else:
                sep = "\t"
                if exprs.endswith("csv"):
                    sep = ","
                # just txt file like input
                rank_metric = pd.read_csv(exprs, comment="#", index_col=0, sep=sep)
                if rank_metric.shape[1] == 1:
                    # rnk file like input
                    rank_metric.columns = rank_metric.columns.astype(str)
            # select numbers
            rank_metric = rank_metric.select_dtypes(include=[np.number])
        else:
            raise Exception("Error parsing gene ranking values!")

        if rank_metric.isnull().any().sum() > 0:
            self._logger.warning("Input data contains NA, filled NA with 0")
            rank_metric = rank_metric.fillna(0)

        if rank_metric.index.duplicated().sum() > 0:
            self._logger.warning(
                "Found duplicated gene names, values averaged by gene names!"
            )
            rank_metric = rank_metric.groupby(level=0).mean()

        return rank_metric

    def run(self):
        """run entry"""

        self._logger.info("Parsing data files for GSVA.............................")
        # load data
        df = self.load_data()
        if self.rnaseq:
            self._logger.info("Poisson kernel selected. Clip negative values to 0 !")
            df = df.clip(lower=0)

        self.data = df
        # normalized samples, and rank
        # filtering out gene sets and build gene sets dictionary
        gmt = self.load_gmt(gene_list=df.index.values, gmt=self.gene_sets)
        self.gmt = gmt
        self._logger.info(
            "%04d gene_sets used for further statistical testing....." % len(gmt)
        )
        # start analysis
        self._logger.info("Start to run GSVA...Might take a while................")

        assert self.min_size <= self.max_size
        if self._outdir:
            mkdirs(self.outdir)

        gsum = gsva_rs(
            df.index.values.tolist(),
            df.values.tolist(),
            gmt,
            self.kernel,
            self.rnaseq,
            self.mx_diff,
            self.abs_rnk,
            self.tau,
            self.min_size,
            self.max_size,
            self._threads,
        )
        self.to_df(gsum.summaries, gmt, df, gsum.indices)
        self.ranking = [rnk[ind] for rnk, ind in zip(gsum.rankings, gsum.indices)]
        self._logger.info("Done")
