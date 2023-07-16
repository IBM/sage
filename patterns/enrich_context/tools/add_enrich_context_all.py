import argparse
import os

from add_enrich_context import Mapping, add_repo_info_from_inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TODO")
    parser.add_argument("-s", "--sage-dir", help="")
    parser.add_argument("-w", "--wisdom", help="")
    parser.add_argument("-o", "--output-dir", help="")
    args = parser.parse_args()

    # result_dir = /tmp/workdir3/resultsを受け取る
    # out_dir = /tmp/aaaagを受け取る
    # src_type = "GitHub-RHIBM"を受け取る
    # w_ftdataを受け取る
    # w_ftdataからw_ftdata_for_the_src_typeのjsonを保管
    # w_ftdata_for_the_src_typeからrepo_namesを計算する
    # for all repo_names
    #    out_dir_for_the_repo = os.path.join(out_dir, src_type, repo_name)
    #    w_ftdata_for_the_repoを計算し保管
    #    sage_dir_for_the_repo = os.path.join(result_dir, src_type, repo_name)
    #    sage_dirがなければnew_contextは空
    # python patterns/enrich_context/tools/add_enrich_context.py 
    #  --sage-dir (sage_dir_for_the_repo)
    #  --wisdom (w_ftdata_for_the_repo.json)
    #  --output-dir (out_dir_for_the_repo)

    # 最後に、
    # for all repo_names
    #    out_dir_for_the_repo = os.path.join(out_dir, src_type, repo_name)
    #    新ftdataを取得してmerge




    sage_dir = args.sage_dir
    if not os.path.isdir(sage_dir):
        print(f"no sage_dir exist: {sage_dir}")

    inventory_file = os.path.join(sage_dir, "yml_inventory.json")
    sage_ftdata = os.path.join(sage_dir, "ftdata.json")
    tmp_sage_ftdata = os.path.join(sage_dir, "ftdata-modified.json") # with correct path

    wisdom_input = args.wisdom
    output_dir = args.output_dir

    add_repo_info_from_inventory(inventory_file, sage_ftdata, tmp_sage_ftdata)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    m = Mapping(output_dir)
    m.run(tmp_sage_ftdata, wisdom_input)
