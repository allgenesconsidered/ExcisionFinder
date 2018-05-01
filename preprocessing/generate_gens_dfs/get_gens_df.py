#!/usr/bin/env python3
# Rewriting `get_chr_tables.sh` in python
# -*- coding: utf-8 -*-
"""
get_gens_dfs.py generates a table (tsv file) listing all variants in a defined interval for a specified 
individual (based on input VCF file). This basically reformats genotypes from VCF for easier 
processing later when designing sgRNAs.
Written in Python v 3.6.1.
Kathleen Keough et al 2017-2018.

Usage:
	get_gens_dfs.py <vcf_file> <locus> <out> [-f] [--bed] [--chrom]

Arguments:
	vcf_file           The sample vcf file, separated by chromosome. BCF also supported. 
	locus			   Locus from which to pull variants, in format chromosome:start-stop, or a BED file, 
					   in which case you must specify --bed
	out				   The name for the output file and directory in which to save the output files.
Options:
	-f                 If this option is specified, keeps homozygous variants in output file. 
					   Therefore, downstream this will generate both allele-specific and non-
					   allele-specific sgRNAs.
	--bed              Indicates that a BED file is being used in place of a locus.
	--chrom            Run on entire chromosome, e.g. for 1KGP analysis. If specified, just put the chromosome
	                   in for <locus>.
"""
import pandas as pd
from docopt import docopt
import subprocess, os, sys
import regex as re
from io import StringIO

__version__='0.0.2'

REQUIRED_BCFTOOLS_VER = 1.5

def norm_chr(chrom_str, vcf_chrom):
	chrom_str = str(chrom_str)
	if not vcf_chrom:
		return chrom_str.replace('chr','')
	elif vcf_chrom:
		return('chr' + chrom_str)

def check_bcftools():
	""" 
	Checks bcftools version, and exits the program if the version is incorrect
	"""
	version = subprocess.run("bcftools -v | head -1 | cut -d ' ' -f2", shell=True,\
	 stdout=subprocess.PIPE).stdout.decode("utf-8").rstrip()
	if float(version) >= REQUIRED_BCFTOOLS_VER:
		print(f'bcftools version {version} running')

	else: 
		print(f"Error: bcftools must be >=1.5. Current version: {version}")
		exit()

def fix_multiallelics(cell):
	"""
	bcftools doesn't complete splitting of multiallelic variant sites.
	:param cell: genotype, str.
	:return: genotype as is if not multiallelic otherwise split multiallelic genotype, str.
	"""
	splitters = [',', ';']
	if any(splitter in str(cell) for splitter in splitters):
		cell = re.split(';|,', cell)[0]
	return cell


def het(genotype):
	# if genotype == '.':
	# 	return False
	gen1, gen2 = re.split('/|\|',genotype)
	return gen1 != gen2


def filter_hets(gens_df):
	"""
	filters for only heterozygous variants
	"""
	genotype_cols = list(set(gens_df.columns).difference(set(['chrom', 'pos', 'ref', 'alt'])))
	gens_df['het'] = gens_df.apply(lambda row: any(het(row[col]) for col in genotype_cols), axis=1)
	out = gens_df.query('het')[['chrom', 'pos', 'ref', 'alt']+genotype_cols]
	return out

def fix_natural_language(name):
	"""
	Fixes NaturalNameWarning given by trying to write an hdf5 column name
	"""
	for ch in r"\`*{}[]()>#+-.!$":
		if ch in name:
			name = name.replace(ch,"_")
	return name

def main(args):

	print(args)
	vcf_in = args['<vcf_file>']

	# Check if bcftools is installed, and then check version number
	check_bcftools()

	# if input is a BED file, run recursively
	if args['--bed']:
		bed_file = args['<locus>']
		out = args['<out>']
		print(f'Analyzing BED file {bed_file}')
		bed_df = pd.read_csv(bed_file, sep='\t', header=0)
		vcf_chrom = subprocess.Popen(f'bcftools view -H {vcf_in} | cut -f1 | head -1', shell=True, 
			stdout=subprocess.PIPE).communicate()[0].decode("utf-8").strip()
		# See if chrom contains chr
		chrstart = vcf_chrom.startswith('chr')

		bed_chrom = str(bed_df.iloc[0,0])
		bed_note = bed_chrom.startswith('chr')

		if bed_note != chrstart:
			raise ValueError(f'Chromosome notations differ between BED file ({bed_chrom}) and VCF/BCF ({vcf_chrom}).')
		# removes or adds "chr" based on analyzed VCF
		#bed_df['chr'] = [ norm_chr(chrom, chrstart) for chrom in bed_df['chr'].tolist() ]

		# write to temp file
		#bed_df.to_csv(f'{out}_temp.bed', index=False, sep='\t', header=False)

		# gets genotypes at locus of interest, excluding those where 1+ samples missing a genotype call

		# if option -f specified, indicating to keep homozygous variants, do so
		if args['-f']:
			bcl_v=f"bcftools view -g ^miss -R {bed_file} {args['<vcf_file>']}"
		else:
			bcl_v=f"bcftools view -g ^miss -g het -R {bed_file} {args['<vcf_file>']}"

		# Pipe for bcftools
		bcl_view = subprocess.Popen(bcl_v,shell=True, stdout=subprocess.PIPE)
		# splits multiallelic sites into multiple lines
		bcl_norm = subprocess.Popen("bcftools norm -m -",shell=True, stdin=bcl_view.stdout, stdout=subprocess.PIPE)
		bcl_query = subprocess.Popen("bcftools query -f '%CHROM\t%POS\t%REF\t%ALT{0}\n'",shell=True,
		 stdin=bcl_norm.stdout, stdout=subprocess.PIPE)
		bcl_query.wait() # Don't do anything else untill bcl_query is done running.

		# output  
		raw_dat = pd.read_csv(StringIO(bcl_query.communicate()[0].decode("utf-8")), sep='\t')
		raw_dat.columns = ['chrom','pos','ref','alt']

		# save to HDF
		raw_dat.to_hdf(f'{out}_gens.h5','all', data_columns=True)
		#os.remove(f'{out}_temp.bed')
		print('finished')


		# hdf_out = pd.HDFStore(args['<out>'] + '.h5')
		# for index, row in bed_df.iterrows():
			
		# 	# check whether chromosome in VCF file includes "chr" in chromosome
		# 	vcf_chrom = str(subprocess.Popen(f'gzcat {vcf_in} | tail -1 | cut -f1', shell=True))

		# 	if vcf_chrom.startswith('chr'):
		# 		chrstart = True
		# 	else:
		# 		chrstart = False

		# 	# See if chrom contains chr
		# 	chrom = str(row['chr'])
		# 	start = row['start']
		# 	stop = row['stop']

		# 	# removes or adds "chr" based on analyzed VCF
		# 	chr_name = norm_chr(chrom, chrstart)

		# 	# gets genotypes at locus of interest, excluding those where 1+ samples missing a genotype call
		# 	# if option -f specified, indicating to keep homozygous variants, do so
		# 	if args['-f']:
		# 		bcl_v=f"bcftools view -g ^miss -r {chr_name}:{str(start)}-{str(stop)} {args['<vcf_file>']}"
		# 	else:
		# 		bcl_v=f"bcftools view -g ^miss -g het -r {chr_name}:{str(start)}-{str(stop)} {args['<vcf_file>']}"
			
		# 	# Pipe for bcftools
		# 	bcl_view = subprocess.Popen(bcl_v,shell=True, stdout=subprocess.PIPE)
		# 	# splits multiallelic sites into multiple lines
		# 	bcl_norm = subprocess.Popen("bcftools norm -m -",shell=True, stdin=bcl_view.stdout, stdout=subprocess.PIPE)
		# 	bcl_query = subprocess.Popen("bcftools query -f '%CHROM\t%POS\t%REF\t%ALT{0}\n'",shell=True,
		# 	 stdin=bcl_norm.stdout, stdout=subprocess.PIPE)
		# 	bcl_query.wait() # Don't do anything else untill bcl_query is done running.

		# 	# output  
		# 	raw_dat = StringIO(bcl_query.communicate()[0].decode("utf-8"))

		# 	# temp_file_name=f"{args['<out>']}{str(chrom)}_prechrtable.txt"
		# 	# with open(temp_file_name, 'w') as f:
		# 	# 	f.write(raw_dat)
		# 	# 	f.close()

		# 	# generate output format
		# 	vars = pd.read_csv(raw_dat, sep='\t', header=None, names=['chrom', 'pos', 'ref', 'alt'],
		# 		usecols=['chrom', 'pos', 'ref', 'alt'])

		# 	if vars.empty and args['-f']:
		# 		print('No variants in this region for this individual. Moving on.')
		# 		# os.remove(temp_file_name)
		# 		continue
		# 	elif vars.empty and not args['-f']:
		# 		print('No heterozygous variants in this region for this individual. Moving on.')
		# 		# os.remove(temp_file_name)
		# 		continue

		# 	# # this looks like it might be redundant now
		# 	# if 'chr' in str(vars.chrom.iloc[0]):
		# 	# 	vars['chrom'] = vars['chrom'].map(lambda x: norm_chr(x))

		# 	# I'm pretty sure this is redundant too with alt{0} part in bcftools command
		# 	# if args['-f']:
		# 	# 	vars_fixed = vars.applymap(fix_multiallelics)
		# 	# this was made redundant with change to bcftools argument above
		# 	# else:
		# 	# 	vars_fixed = filter_hets(vars.applymap(fix_multiallelics))

		# 	locus_name = row['locus']
		# 	print(locus_name)
		# 	hdf_out.put(fix_natural_language(locus_name), vars)
		# 	# hdf_out.put(row['locus'],vars_fixed, format='t', data_columns=True, complib='blosc')
		# 	print(f'{locus_name} done.')
			# os.remove(temp_file_name)
		# hdf_out.close()

	elif args['<locus>'].endswith('.bed') or args['<locus>'].endswith('.BED'):
		print('Must specify --bed if inputting a BED file. Exiting.')
		exit()
	elif args['--chrom']:
		print('Running get_chr_tables.py on entire chromosome. This might take awhile.')
		# get locus info
		# check whether chromosome in VCF file includes "chr" in chromosome
		vcf_chrom = str(subprocess.Popen(f'gzcat {vcf_in} | tail -1 | cut -f1', shell=True))
		chrom = norm_chr(args['<locus>'])

		samples = str(subprocess.Popen(f'bcftools query -l {args["<vcf_file>"]}', shell=True, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")).split('\n')
		samples = list(filter(None,samples))
		n_samples = len(samples)

		print(f'There are {n_samples} samples in the provided VCF.')

		bcl_v=f"bcftools view -r {chrom} {args['<vcf_file>']}"
		
		# Pipe for bcftools
		bcl_view = subprocess.Popen(bcl_v,shell=True, stdout=subprocess.PIPE)
		bcl_norm = subprocess.Popen("bcftools norm -m -",shell=True, stdin=bcl_view.stdout, stdout=subprocess.PIPE)
		bcl_query = subprocess.Popen("bcftools query -f '%CHROM\t%POS\t%REF\t%ALT[\t%TGT]\n'",shell=True,
		 stdin=bcl_norm.stdout, stdout=subprocess.PIPE)
		bcl_query.wait() # Don't do anything else untill bcl_query is done running.

		# output  
		raw_dat = bcl_query.communicate()[0].decode("utf-8")

		temp_file_name=f"{args['<outdir>']}/{str(chrom)}_prechrtable.txt"
		with open(temp_file_name, 'w') as f:
			f.write(raw_dat)
			f.close()

		genotype_list = []
		for sample in samples:
			genotype_list.append(f'{sample}')

		# Append fix_chr_tables.py
		name_list = ['chrom', 'pos', 'ref', 'alt'] + genotype_list
		vars = pd.read_csv(temp_file_name, sep='\t', header=None, names=name_list,
			usecols=name_list)

		if vars.empty and args['-f']:
			print('No variants in this region for this individual. Exiting.')
			exit()
		elif vars.empty and not args['-f']:
			print('No heterozygous variants in this region for this individual. Exiting.')
			exit()

		if args['-f']:
			vars_fixed = vars.applymap(fix_multiallelics)
		else:
			# gets rid of variants where not at least one ind has a het variant
			vars_fixed = filter_hets(vars.applymap(fix_multiallelics))

		if args['<name>']:
			outname = f"{args['<name>']}.hdf5"
		else:
			outname = f'chr{chrom}_gens.hdf5'

		vars_fixed.to_hdf(os.path.join(args['<outdir>'], outname), 'all', format='t', data_columns=True, complib='blosc')

		os.remove(temp_file_name)
	else:
		print('Running single locus')

		# get locus info
		# check whether chromosome in VCF file includes "chr" in chromosome
		vcf_chrom = str(subprocess.Popen(f'gzcat {vcf_in} | tail -1 | cut -f1', shell=True,
			stdout=subprocess.PIPE).communicate()[0].decode("utf-8"))
		locus = args['<locus>']
		chrom = norm_chr(locus.split(':')[0],vcf_chrom.startswith('chr'))

		samples = str(subprocess.Popen(f'bcftools query -l {args["<vcf_file>"]}', shell=True, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")).split('\n')
		samples = list(filter(None,samples))
		samples = [ fix_natural_language(name) for name in samples ]

		n_samples = len(samples)

		print(f'There are {n_samples} samples in the provided VCF.')

		bcl_v=f"bcftools view -r {chrom}:{locus.split(':')[1]} {args['<vcf_file>']}"
		
		# Pipe for bcftools
		bcl_view = subprocess.Popen(bcl_v,shell=True, stdout=subprocess.PIPE)
		bcl_norm = subprocess.Popen("bcftools norm -m -",shell=True, stdin=bcl_view.stdout, stdout=subprocess.PIPE)
		bcl_query = subprocess.Popen("bcftools query -f '%CHROM\t%POS\t%REF\t%ALT[\t%TGT]\n'",shell=True,
		 stdin=bcl_norm.stdout, stdout=subprocess.PIPE)
		bcl_query.wait() # Don't do anything else untill bcl_query is done running.

		# output  
		raw_dat = bcl_query.communicate()[0].decode("utf-8")

		temp_file_name=f"{args['<out>']}_prechrtable.txt"
		with open(temp_file_name, 'w') as f:
			f.write(raw_dat)
			f.close()

		genotype_list = []
		for sample in samples:
			genotype_list.append(f'{sample}')

		# Append fix_chr_tables.py
		name_list = ['chrom', 'pos', 'ref', 'alt'] + genotype_list
		vars = pd.read_csv(temp_file_name, sep='\t', header=None, names=name_list,
			usecols=name_list)

		if vars.empty and args['-f']:
			print('No variants in this region for this individual. Exiting.')
			exit()
		elif vars.empty and not args['-f']:
			print('No heterozygous variants in this region for this individual. Exiting.')
			exit()

		if args['-f']:
			vars_fixed = vars.applymap(fix_multiallelics)
		else:
			# gets rid of variants where not at least one ind has a het variant
			vars_fixed = filter_hets(vars.applymap(fix_multiallelics))

		outname = f"{args['<out>']}.hdf5"



		vars_fixed.to_hdf(outname, 'all', format='t', data_columns=True, complib='blosc')

		os.remove(temp_file_name)


if __name__ == '__main__':
	arguments = docopt(__doc__, version='0.2')
	main(arguments)
