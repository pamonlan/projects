#/usr/bin/env python
"""Prepare input configuration files for variants by priority or family.

Groups into family based calling.
"""
import collections
import csv
import datetime
import glob
import os
import sys

import yaml

def main(config_file, env):
    with open(config_file) as in_handle:
        config = yaml.load(in_handle)
        config = _add_env_kvs(config, env)
        config = _add_base_dir(config)
    idremap = read_remap_file(config["idmapping"])
    famsamples = get_families(config["priority"], config["params"])
    famsamples = sorted(famsamples.iteritems(), key=lambda xs: len(xs[1]), reverse=True)
    baminfo = get_bam_files(config["inputs"], idremap)
    if config["params"]["max_samples"]:
        for i, g in enumerate(split_families(famsamples, config["params"]["max_samples"])):
            name = "g%s" % (i+1)
            write_config(g, baminfo, name, config["params"]["name"], config["out"],
                         config)
    else:
        write_config(famsamples, baminfo, None, config["params"]["name"], config["out"],
                     config)

# ## Write output configurations

def write_config(g, baminfo, name, group_name, outbase, config):
    outdir = os.path.dirname(outbase)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)
    if name:
        base, ext = os.path.splitext(outbase)
        outfile = "%s-%s%s" % (base, name, ext)
    else:
        outfile = outbase
    out = {"upload": {"dir": "../final"},
           "fc_date": datetime.datetime.now().strftime("%Y-%m-%d"),
           "fc_name": "alz-%s%s" % (group_name, "-%s" % name if name else ""),
           "details": []}
    for family, samples in g:
        for sample in samples:
            if sample in baminfo:
                cur = {"algorithm": {"aligner": "bwa",
                                     "align_split_size": 20000000,
                                     "variantcaller": "freebayes",
                                     "mark_duplicates": "samtools",
                                     "recalibrate": False,
                                     "realign": False,
                                     "quality_format": "Standard",
                                     "coverage": config["coverage"],
                                     "coverage_interval": "genome",
                                     "coverage_depth": "high"},
                       "analysis": "variant2",
                       "genome_build": "GRCh37",
                       "metadata": {"batch": str(family)},
                       "description": str(sample),
                       "files": [baminfo[sample]["bam"]]}
                out["details"].append(cur)
            else:
                print("BAM file missing for %s" % sample)
    with open(outfile, "w") as out_handle:
        yaml.dump(out, out_handle, allow_unicode=False, default_flow_style=False)
    return outfile

def split_families(famsamples, max_samples):
    """Split families into groups that fit for processing.
    """
    orig_size = sum(len(s) for f, s in famsamples)
    for f, s in famsamples:
        print f, s
    groups = []
    cur_group = []
    cur_size = 0
    while len(famsamples) > 0:
        next_name, next_samples = famsamples.pop(0)
        if cur_size + len(next_samples) > max_samples:
            groups.append(cur_group)
            cur_group = []
            cur_size = 0
        cur_group.append((next_name, next_samples))
        cur_size += len(next_samples)
    if len(cur_group) > 0:
        groups.append(cur_group)
    group_size = 0
    for g in groups:
        group_size += sum(len(s) for f, s in g)
    assert orig_size == group_size, (orig_size, group_size)
    return groups

# ## Priority file

def _check_sample(fam_id, priority, params):
    if params.get("priority") is not None:
        if priority and int(priority) == params["priority"]:
            return True
    elif params.get("families"):
        if fam_id in params["families"]:
            return True
    return False

def get_families(in_file, params):
    """Retrieve samples in specific priorities or families, grouped by family.
    """
    samples = collections.defaultdict(list)
    with open(in_file) as in_handle:
        reader = csv.reader(in_handle)
        header = reader.next() # header
        for parts in reader:
            fam_id, sample_id, priority = parts[1:4]
            status_flag = parts[16]
            if status_flag != "Exclude":
                if _check_sample(fam_id, priority, params):
                    if sample_id not in samples[fam_id]:
                        samples[fam_id].append(sample_id)
    return dict(samples)

# ## Directory and name remapping

def dir_to_sample(dname, idremap):
    vcf_file = os.path.join(dname, "Variations", "SNPs.vcf")
    bam_file = os.path.join(dname, "Assembly", "genome", "bam", "%s.bam" % os.path.split(dname)[-1])
    if not os.path.exists(bam_file):
        print "BAM file missing", bam_file
        return None
    with open(vcf_file) as in_handle:
        for line in in_handle:
            if line.startswith("#CHROM"):
                illumina_id = line.split("\t")[-1].replace("_POLY", "").rstrip()
                if idremap.get(illumina_id) is None:
                    print "Did not find remap", illumina_id
                return {"id": idremap.get(illumina_id), "dir": dname,
                        "illuminaid": illumina_id,
                        "bam": bam_file}
    raise ValueError("Did not find sample information in %s" % vcf_file)

def get_bam_files(fpats, idremap):
    out = {}
    for fpat in fpats:
        for dname in glob.glob(fpat):
            if os.path.isdir(dname):
                x = dir_to_sample(dname, idremap)
                if x:
                    out[x["id"]] = x
    return out

def read_remap_file(in_file):
    out = {}
    with open(in_file) as in_handle:
        in_handle.next() # header
        for line in in_handle:
            patient_id, illumina_id = line.rstrip().split()
            out[illumina_id] = patient_id
    return out

# ## Utils

def _add_env_kvs(config, env):
    """Add key values specific to the running environment.
    """
    for k, val in config[env].iteritems():
        config[k] = val
    return config

def _add_base_dir(config):
    for k in ["idmapping", "priority", "coverage"]:
        config[k] = os.path.join(config["base_dir"], config[k])
    return config

if __name__ == "__main__":
    main(*sys.argv[1:])

