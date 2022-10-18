import os
import sys
import argparse
from subprocess import Popen, PIPE, getstatusoutput
import shutil
from urllib.parse import quote
from message import *

FuzzProjectDataPath = "./AFL_Fuzz_Datas"
# Message Send Service
Bark_msg_enabled = True
Ding_msg_enabled = False


# Regular Colour
Norm='\033[0m'
Black='\033[0;30m'        # Black
Red='\033[0;31m'          # Red
Green='\033[0;32m'        # Green
Yellow='\033[0;33m'       # Yellow
Blue='\033[0;34m'         # Blue
Purple='\033[0;35m'       # Purple
Cyan='\033[0;36m'         # Cyan
White='\033[0;37m'        # White

AFL_utils_enabled = False
loglevel = 0
verbose = False


def banner():
    print("""
==========================================================
 _                     ____               _
| |    __ _ _____   _ / ___|_ __ __ _ ___| |__   ___ _ __
| |   / _` |_  / | | | |   | '__/ _` / __| '_ \ / _ \ '__|
| |__| (_| |/ /| |_| | |___| | | (_| \__ \ | | |  __/ |
|_____\__,_/___|\__, |\____|_|  \__,_|___/_| |_|\___|_|
                |___/
==========================================================
    """)


"""
    check if command exist
"""
def command_check(cmd):
    if getstatusoutput(cmd)[0] == 127:
        print(Red, "[!]", Norm, "Command not Found:", Red, cmd, Norm)
        return False
    return True


def path_check(path):
    if not os.path.exists(path):
        print(Red, "[!]", Norm, "No such directory:", Red, path, Norm)
        exit(1)

"""
    checking the environment
"""
def env_check():
    global AFL_utils_enabled
    global loglevel
    print(Cyan, "[*]", Norm, "Checking Environment...")
    if not command_check("afl-fuzz"):
        exit(1)
    if command_check("afl-collect"):
        AFL_utils_enabled = True
    else:
        loglevel = 0
    print(Green, "[*]", Norm, "Pass checking environment.")


def watch_output(software, listen_time):
    listen_path = os.path.join(FuzzProjectDataPath, software) if software is not None else FuzzProjectDataPath
    path_check(listen_path)
    print(Green, "[+]", Norm, "Listen:", Green, listen_path, Norm)

    # Search for crashes directory
    process = Popen(["find", listen_path, "-type" ,"d" ,"-name", "crashes"], stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        if process.returncode == 1:
            print(Red, "[!]", "Can not found the crashes folder, please check the data path if is correct.", Norm)
            exit(1)
        raise RuntimeError(stderr.decode())
    
    collect_list = {}
    # find if has new Crashes
    for crash_fold in stdout.splitlines():
        crash_fold = crash_fold.decode()
        crash_software_name = crash_fold.split("/")[-4]

        process = Popen(["find", crash_fold, "-type", "f", "-mmin", f"-{listen_time}"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        if stdout:
            if crash_software_name not in collect_list:
                collect_list[crash_software_name] = {
                    "crash_fold_path": crash_fold,
                    "collection_fold_path": "",
                    "output_fold_path": "",
                    "new_crashes_num": 1,
                }
            else:
                collect_list[crash_software_name]["new_crashes_num"] += 1

            print(Green, "[+]", Norm, "Find new Crash from", Yellow, crash_software_name, Norm)
            if AFL_utils_enabled:
                # copy crashes/README.txt to collect folder
                crash_README = os.path.join(crash_fold, "README.txt")
                crash_software_collection_folder = os.path.abspath(os.path.join(crash_fold, "../../../collections"))
                collect_list[crash_software_name]["output_fold_path"] = os.path.abspath(os.path.join(crash_fold, "../../../output"))
                collect_list[crash_software_name]["collection_fold_path"] = crash_software_collection_folder

                if os.path.exists(crash_README):
                    if not os.path.exists(crash_software_collection_folder):
                        print(Yellow, "[+]", Norm, f"Create new collection folder -- {crash_software_name}")
                        os.mkdir(crash_software_collection_folder)
                    if os.path.exists(os.path.join(crash_software_collection_folder, "README.txt")):
                        shutil.copyfile(crash_README, crash_software_collection_folder)
                else:
                    print(Red, "[!] Can not find the crashes/README.txt", Norm)
        
    # print(collect_list)

    if collect_list != {} and loglevel == 0:
        msg_title = "发现新的Crash!"
        msg_content = ""
        for item in collect_list:
            msg_content += quote(f"Software {item} find {collect_list[item]['new_crashes_num']} new crashes.\n")
        if Bark_msg_enabled:
            send_bark(msg_title, msg_content)
        if Ding_msg_enabled:
            send_dingtalk(msg_title, msg_content)
        if verbose:
            print(Yellow, "[!]", Norm, f"Send Message--> title: {msg_title}, content: {msg_content}")

    # TODO invoke afl-collcet
    collect_list_ = []
    if collect_list != {} and AFL_utils_enabled:
        print(Cyan, "[+]", Norm, "Invoke afl-collcet....")
        for item in collect_list:
            print(Green, "[+]", Norm, "Now:", item)
            try:
                with open(os.path.join(collect_list[item]["crash_fold_path"], "README.txt"), "r") as f:
                    cmd = f.readlines()[2].strip()
                    cmds = cmd.split()
                    arg_input = collect_list[item]["output_fold_path"]
                    arg_output = collect_list[item]["collection_fold_path"]
                    arg_cmd = cmds[cmds.index("--")+1:]

                    process = Popen(["find", arg_output, "-type", "f", "!", "-name", "gdb_script"], stdout=PIPE, stderr=PIPE)
                    stdout, stderr = process.communicate()
                    old_num = len(stdout.split(b"\n"))

                    # run afl-collect command:
                    run_args = ["afl-collect", "-j", "8", "-e", "gdb_script", "-r", "-rr", arg_input, arg_output, "--"]
                    run_args.extend(arg_cmd)
                    if verbose:
                        print(Yellow, "Log(command):", Norm, ' '.join(run_args))
                    env_tmp = os.environ.copy()
                    env_tmp["ASAN_OPTIONS"] = "abort_on_error=1:symbolize=0"
                    if verbose:
                        process = Popen(run_args, env=env_tmp)
                        process.wait(timeout=600)
                    else:
                        process = Popen(run_args, stdout=PIPE, stderr=PIPE, env=env_tmp)
                        stdout, stderr = process.communicate(timeout=600)
                    # if verbose:
                    #     print(Yellow, "Log(afl-collect_stdout):", Norm, stdout.decode())
                    f.close()
                
                process = Popen(["find", arg_output, "-type", "f", "!", "-name", "gdb_script"], stdout=PIPE, stderr=PIPE)
                stdout, stderr = process.communicate()
                if verbose:
                    print(Yellow, "Log(find_stdout):", Norm, stdout.decode())
                if stdout:
                    
                    new_num = len(stdout.split(b"\n"))
                    if new_num-old_num > 0:
                        collect_list_.append((item, new_num-old_num)) 
            except Exception as e:
                print(Red, "[!]", e, Norm)

        if collect_list_ != []:
            msg_title = "发现新的Crash(By afl-collect)!"
            msg_content = ""
            for item in collect_list_:
                msg_content += quote(f"Software {item[0]} find {item[1]} new crashes.\n")
            if Bark_msg_enabled:
                send_bark(msg_title, msg_content)
            if Ding_msg_enabled:
                send_dingtalk(msg_title, msg_content)
            if verbose:
                print(Yellow, "[!]", Norm, f"Send Message--> title: {msg_title}, content: {msg_content}")

    print(Green, "[*]", Norm, "Finish invoke afl-collect.")            
    # TODO invoke afl-tmin

def parse_args():
    parser = argparse.ArgumentParser(description="Lazycrasher opts")
    parser.add_argument('-d', '--data-path', type=str, help=f"Path to save fuzz projects' input & output data [Default: {FuzzProjectDataPath}]")
    parser.add_argument('-t', '--time', type=int, help="Set the time from the current time when the search crash occurs")
    parser.add_argument('-s', '--software', type=str, help="Software to search for fuzz projects, Default: None (Search All fuzz projects)")
    parser.add_argument('-l', '--log-level', type=int, help="Level of Sending message: [0] Send message when find new crashes(not collect) [Default] | [1] Send message when find useful crashes (after collect)")
    parser.add_argument('-v', '--verbose', action='store_true', default=False, help="Show all debug messages")
    return parser.parse_args()


if __name__ == '__main__':
    # banner()
    args = parse_args()
    if args.data_path:
        FuzzProjectDataPath = args.data_path
    else:
        print(Yellow, "[*]", Norm, "Not set the Data path. Using Default data path:", Yellow, FuzzProjectDataPath, Norm)
    listen_time = args.time if args.time else 10
    software = args.software
    loglevel = args.log_level if args.log_level == 1 else 0
    verbose = args.verbose
    
    env_check()

    try:
        watch_output(software=software, listen_time=listen_time)
    except Exception as e:
        print(e)