#!/bin/bash
#$ -e {workdir}
#$ -S /bin/bash
# properties = {properties}
source /data/results/gusev/software/exports

snakemake --snakefile {workflow.snakefile} \
--force -j{cores} \
--directory {workdir} --nocolor --notemp --quiet --nolock {job.output} \
&& touch "{jobfinished}" || touch "{jobfailed}"
exit 0
