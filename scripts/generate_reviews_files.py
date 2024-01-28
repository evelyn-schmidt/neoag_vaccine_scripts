import argparse
import csv
import pandas as pd
import sys
from Bio.SeqUtils.ProtParam import ProteinAnalysis
import re

'''
Write a script to create the files for the Case Final Reports
- Sample Peptides 51-mer
- SAMPLE.Annotated.Neoantigen_Candidates.xlsx

Example Run:
python3 ../scripts/generate_reviews_files.py -a itb-review-files/*.xlsx -c generate_protein_fasta/candidates/annotated_filtered.vcf-pass-51mer.fa.manufacturability.tsv -classI gcp_immuno/final_results/pVACseq/mhc_i/jlf-100-053-tumor-exome.all_epitopes.aggregated.tsv -classII gcp_immuno/final_results/pVACseq/mhc_ii/jlf-100-053-tumor-exome.all_epitopes.aggregated.ClassII.tsv  -samp JLF-1
00-051 -o manual_review/
'''

# ---- PARSE ARGUMENTS -------------------------------------------------------
# Parses command line arguments
# Enables user help
def parse_arguments():
    # Parse command line arugments
    parser = argparse.ArgumentParser(description='Create the file needed for the neoantigen manuel review')

    parser.add_argument('-a',
                        help='The path to the ITB Reviewed Candidates excel file', required=True)
    parser.add_argument('-c',
                        help='The path to candidates annotated_filtered.vcf-pass-51mer.fa.manufacturability.tsv from the generate_protein_fasta script', required=True)
    parser.add_argument('-classI',
                        help='The path to the classI all_epitopes.aggregated.tsv used in pVACseq', required=True)
    parser.add_argument('-classII',
                        help='The path to the classII all_epitopes.aggregated.tsv used in pVACseq', required=True)
    parser.add_argument('-samp',
                        help='The name of the sample', required=True)
    parser.add_argument('-o',
                        help='the path to output folder')


    # The name of the final results folder 
    parser.add_argument('-f', "--fin_results", help="Name of the final results folder in gcp immuno")

    return(parser.parse_args())

# Fucnction to break the pepetides ID on the . to extract gene and AA information
def extract_info(value):
    parts = value.split('.')
    result = '.'.join([parts[2], parts[3], parts[4]])
    return result

# Function to rearrange string so that G518D looks like 518G/D
def rearrange_string(s):
    match = re.match(r'([A-Za-z]+)([\d-]+)([A-Za-z]*)', s)
    if match:
        letters_before = match.group(1)
        numbers = match.group(2)
        letters_after = match.group(3)
                
        return f"{numbers}{letters_before}/{letters_after}"
    else:
        return s
    
# Function to calculate molecular weight---------------------------------------
def calculate_molecular_weight(peptide):
    analyzed_seq = ProteinAnalysis(peptide)
    return analyzed_seq.molecular_weight()

# Function to make id column unique -------------------------------------------
def make_column_unique(df, column_name):
    seen_values = set()
    new_values = []

    for value in df[column_name]:
        if value in seen_values:
            suffix = 1
            while f"{value}.{suffix}" in seen_values:
                suffix += 1
            unique_value = f"{value}.{suffix}"
        else:
            unique_value = value

        seen_values.add(unique_value)
        new_values.append(unique_value)

    df[column_name] = new_values
    return df


def main():

    args = parse_arguments()
    
    # Creating the Reviewed Candidates Sheet
    reviewed_candidates = pd.read_excel(args.a)

    # Check if the first row is blank
    if reviewed_candidates.iloc[0].isnull().all():
        # Remove the first row if it's blank
        reviewed_candidates = reviewed_candidates[1:]
        # If there are still rows in the DataFrame, proceed with the operations
        if not reviewed_candidates.empty:
            # Set the columns to the values of the first row
            reviewed_candidates.columns = reviewed_candidates.iloc[0]
            # Skip the first row (which is now the column names)
            reviewed_candidates = reviewed_candidates[1:]
            # Reset the index of the DataFrame
            reviewed_candidates = reviewed_candidates.reset_index(drop=True)

    reviewed_candidates = reviewed_candidates[reviewed_candidates.Evaluation != "Pending"]
    reviewed_candidates = reviewed_candidates[reviewed_candidates.Evaluation != "Reject"]

    reviewed_candidates = reviewed_candidates.rename(columns={'Comments':'pVAC Review Comments'})
    reviewed_candidates["Variant Called by CLE Pipeline"] = " "
    reviewed_candidates["IGV Review Comments"] = " "


    # create sorting ID that is gene and transcript to sort in the same order as peptide
    reviewed_candidates['sorting id'] = reviewed_candidates['Gene']  + '.' + reviewed_candidates['Best Transcript']
    # make sure the sorting id column is unique
    reviewed_candidates = make_column_unique(reviewed_candidates, 'sorting id')

    # Creating the Peptides 51mer Sheet -----------------------------------
    peptides = pd.read_csv(args.c, sep="\t")
    peptides =  peptides.drop(['cterm_7mer_gravy_score', 'cysteine_count', 'n_terminal_asparagine', 'asparagine_proline_bond_count', 
                                 'difficult_n_terminal_residue', 'c_terminal_cysteine', 'c_terminal_proline', 'max_7mer_gravy_score'], axis=1)
    peptides["RESTRICTING HLA ALLELE"] = " "

    peptides["CANDIDATE NEOANTIGEN AMINO ACID SEQUENCE MW (CLIENT)"] = peptides["peptide_sequence"].apply(calculate_molecular_weight)

    peptides = peptides.rename(columns={"id":"ID", "peptide_sequence":"CANDIDATE NEOANTIGEN AMINO ACID SEQUENCE WITH FLANKING RESIDUES"})
    peptides["Comments"] = " "
    peptides["CANDIDATE NEOANTIGEN"] = peptides["ID"].apply(lambda x: '.'.join(x.split('.')[:3]))
    peptides["CANDIDATE NEOANTIGEN"] = args.samp + "." + peptides["CANDIDATE NEOANTIGEN"]

    peptides = peptides[["ID", "CANDIDATE NEOANTIGEN", "CANDIDATE NEOANTIGEN AMINO ACID SEQUENCE WITH FLANKING RESIDUES", 
                           "RESTRICTING HLA ALLELE", "CANDIDATE NEOANTIGEN AMINO ACID SEQUENCE MW (CLIENT)", "Comments"]]
    
    # Add the Restricting HLA Alles from Class I and Class II
     # create a dataframe that contains the classI and classII pepetide sequence
         # Create a universal ID by editing the peptide 51mer ID
    peptides.rename(columns={'ID': 'full ID'}, inplace=True)
    peptides['51mer ID'] = peptides['full ID']
    peptides['51mer ID'] = peptides['51mer ID'].apply(lambda x: '.'.join(x.split('.')[1:]))  # Removes the 'MT' from the beginning of ID column
    peptides['51mer ID'] = peptides['51mer ID'].apply(lambda x: '.'.join(x.split('.')[1:]))  # Remives the MT index from the ID column

    def modify_id(x):
        parts = x.split('.')
        
        if 'FS' in parts:
            # If 'FS' is present, remove non-digit characters after the last period
            def is_valid_char(char):
                return char.isdigit() or char == '-' or (char in ['.', '/'] and parts[-1][parts[-1].index(char)+1].isdigit())
            last_part = ''.join(filter(is_valid_char, parts[-1]))
            modified_id = '.'.join(parts[:-1]) + last_part
        else:
            # If 'missense' or other labels are present, remove them
            modified_id = '.'.join(parts[:3] + parts[4:])
        
        return modified_id

    #peptides['51mer ID'] = peptides['51mer ID'].apply(lambda x: '.'.join(x.split('.')[:3]) + '.' + '.'.join(x.split('.')[4:])) # removes the variant label
    peptides['51mer ID'] = peptides['51mer ID'].apply(modify_id)

    classI = pd.read_csv(args.classI, sep="\t")
    classII = pd.read_csv(args.classII, sep="\t")

    classI.rename(columns = {"Best Peptide":"Best Peptide Class I", "Allele":"Class I Allele", 
                             "IC50 MT":"Class I IC50 MT", "%ile MT":"Class I %ile MT", 
                             "Best Transcript":"Class I Best Transcript"}, inplace=True)
    classII.rename(columns = {"Best Peptide":"Best Peptide Class II", "Allele":"Class II Allele", 
                              "IC50 MT":"Class II IC50 MT", "%ile MT":"Class II %ile MT", 
                              "Best Transcript":"Class II Best Transcript"}, inplace=True)

    def rearrange_string(s):
        
        match = re.match(r'([A-Za-z]+)([\d-]+)([A-Za-z]+)', s)
        if match:
            letters_before = match.group(1)
            numbers = match.group(2)
            letters_after = match.group(3)
                
            return f"{numbers}{letters_before}/{letters_after}"
                # Just use the postion for the key to avoid FS problem
            #return f"{numbers}"
        else:
            return s
    
    classI['modified AA Change'] = classI['AA Change'] 
    classI['modified AA Change'] = classI['modified AA Change'].apply(rearrange_string)
    classI['51mer ID'] = classI['Gene'] + '.' + classI['Class I Best Transcript'] + '.' + classI['modified AA Change'] 
    class_sequences = pd.merge(classI[['ID', 'Best Peptide Class I', '51mer ID', 'Pos', 'modified AA Change', 'Class I Allele', "Class I IC50 MT", "Class I %ile MT", "Class I Best Transcript"]], 
                               classII[['ID', 'Best Peptide Class II', 'Class II Allele', "Class II IC50 MT", "Class II %ile MT", "Class II Best Transcript"]], on='ID', how='left')
    class_sequences = class_sequences.drop(columns=['ID'])

    merged_peptide_51mer = pd.merge(peptides, class_sequences, on='51mer ID', how='left')

    # Fill in the Restricting HLA Allele Column
    for index, row in merged_peptide_51mer.iterrows():
        restricting_alleles = ''
        if (float(row['Class I IC50 MT']) < 1000 or float(row['Class I %ile MT']) < 2) and float(row['Class II %ile MT']) < 2: # class I median affinity < 1000 nm OR percentile < 2%
            restricting_alleles = row['Class I Allele'] + '/' + row['Class II Allele']
        elif float(row['Class I IC50 MT']) < 1000 or float(row['Class I %ile MT']) < 2: # classII percentile < 2%
            restricting_alleles = row['Class I Allele']
        elif float(row['Class II %ile MT']) < 2:
            restricting_alleles = row['Class II Allele']
        else:
            restricting_alleles = ''
    
        merged_peptide_51mer.at[index, 'RESTRICTING HLA ALLELE'] = restricting_alleles
    
    merged_peptide_51mer['sorting id'] = merged_peptide_51mer['full ID'].apply(extract_info) # creating a ID to sort reviewed canidates by the order of the 51mer
    merged_peptide_51mer = make_column_unique(merged_peptide_51mer, 'sorting id') # make sure every sorting id is unique

    # Sorting Candidates sheet to be in the same order as Peptides Sheet -------------------------
    reviewed_candidates = reviewed_candidates.set_index('sorting id')
    reviewed_candidates = reviewed_candidates.reindex(index=merged_peptide_51mer['sorting id'])
    reviewed_candidates = reviewed_candidates.reset_index()

    # Dropping the sorting column -------------------------
    reviewed_candidates = reviewed_candidates.drop(columns=['sorting id'])
    merged_peptide_51mer = merged_peptide_51mer.drop(columns=['sorting id'])

    # Writing the files -----------------------------
    if args.o:
        Peptide_file_name = args.o +  "/" + args.samp + "_Peptides_51-mer.xlsx"
    else:
        Peptide_file_name =  args.samp + "_Peptides_51-mer.xlsx"

    merged_peptide_51mer.to_excel(Peptide_file_name, index=False)

    if args.o:
        neoantigen_canidates_file_name = args.o +  "/" + args.samp + ".Annotated.Neoantigen_Candidates.xlsx"
    else:
        neoantigen_canidates_file_name =  args.samp + ".Annotated.Neoantigen_Candidates.xlsx"

    reviewed_candidates.to_excel(neoantigen_canidates_file_name, index=False)


if __name__ == "__main__":
    main()
