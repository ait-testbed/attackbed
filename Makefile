
# ================================
# Makefile for ATB-AECID Testbed
# ================================
# This Makefile automates the execution of Packer and Terragrunt commands 
# for different components of the ATB-AECID testbed.

# PREPARATION:
# to have make find this file from anywhere in the project you have 3 possibilities:

# 1) create a shell alias in your shell configuration file (.bashrc, .zshrc)
# alias make="make -f ~/atb-aecid-testbed/Makefile"

# 2) use MAKEFILES Environment variable in your shell configuration file (.bashrc, .zshrc)
# export MAKEFILES=~/atb-aecid-testbed/Makefile

# 3) create a wrapper in /usr/local/bin/<your-make-command>

# #!/bin/bash
# make -f ~/atb-aecid-testbed/Makefile "$@"

# script needs to be executable: chmod +x /usr/local/bin/<your-make-command>

# Now you can run <your-make-command> instead of "make":
# <your-make-command> packer-firewall


# USAGE:
# - Run Packer for a specific component:
#   make packer-firewall
#   make packer-repository

# - Run Packer in debug mode:
#   make packer-firewall debug=1

# - Run Terragrunt for a specific target:
#   make terragrunt-bootstrap
#   make terragrunt-logging

# - Run Terragrunt in debug mode:
#   make terragrunt-bootstrap debug=1

# NOTE:
# - If your project directory is different, update PACKER_ROOT and TERRAGRUNT_ROOT accordingly.
# - Ensure that Packer and Terragrunt are installed and configured properly before using this Makefile.

.PHONY: packer-firewall packer-repository packer-attacker packer-corpsdns packer-ghostserver packer-kafka \
        packer-linuxshare packer-opensearch packer-userpc packer-videoserver packer-webcam packer-client\
        terragrunt-bootstrap terragrunt-attacker terragrunt-lanturtle terragrunt-logging \
        terragrunt-repository terragrunt-videoserver terragrunt-client

PACKER_CMD := packer build --var-file=default.json .
PACKER_ROOT := ~/atb-aecid-testbed/packer
TERRAGRUNT_CMD := terragrunt apply
TERRAGRUNT_ROOT := ~/atb-aecid-testbed/terragrunt


# If "debug=1" is passed, add "--debug" to the PACKER_CMD
ifneq ($(debug),)
    PACKER_CMD := packer build --debug --var-file=default.json .
	TERRAGRUNT_CMD := terragrunt apply --terragrunt-log-level debug --terragrunt-debug
endif


packer-firewall:
	@echo "Running Packer for firewall..."
	cd $(PACKER_ROOT)/firewall && $(PACKER_CMD)

packer-repository:
	@echo "Running Packer for repository..."
	cd $(PACKER_ROOT)/repository && $(PACKER_CMD)

packer-attacker:
	@echo "Running Packer for attacker..."
	cd $(PACKER_ROOT)/attacker && $(PACKER_CMD)

packer-corpsdns:
	@echo "Running Packer for corpsdns..."
	cd $(PACKER_ROOT)/corpsdns && $(PACKER_CMD)

packer-ghostserver:
	@echo "Running Packer for ghostserver..."
	cd $(PACKER_ROOT)/ghostserver && $(PACKER_CMD)

packer-kafka:
	@echo "Running Packer for kafka..."
	cd $(PACKER_ROOT)/kafka && $(PACKER_CMD)

packer-linuxshare:
	@echo "Running Packer for linuxshare..."
	cd $(PACKER_ROOT)/linuxshare && $(PACKER_CMD)

packer-opensearch:
	@echo "Running Packer for opensearch..."
	cd $(PACKER_ROOT)/opensearch && $(PACKER_CMD)

packer-userpc:
	@echo "Running Packer for userpc..."
	cd $(PACKER_ROOT)/userpc && $(PACKER_CMD)

packer-videoserver:
	@echo "Running Packer for videoserver..."
	cd $(PACKER_ROOT)/videoserver && $(PACKER_CMD)

packer-webcam:
	@echo "Running Packer for webcam..."
	cd $(PACKER_ROOT)/webcam && $(PACKER_CMD)

packer-client:
	@echo "Running Packer for client..."
	cd $(PACKER_ROOT)/client && $(PACKER_CMD)

#----------------- Terragrunt Targets -----------------
terragrunt-bootstrap:
	@echo "Running Terragrunt for bootstrap..."
	cd $(TERRAGRUNT_ROOT)/bootstrap && $(TERRAGRUNT_CMD) 

terragrunt-attacker:
	@echo "Running Terragrunt for attacker..."
	cd $(TERRAGRUNT_ROOT)/attacker && $(TERRAGRUNT_CMD) 

terragrunt-lanturtle:
	@echo "Running Terragrunt for lanturtle..."
	cd $(TERRAGRUNT_ROOT)/lanturtle && $(TERRAGRUNT_CMD) 

terragrunt-logging:
	@echo "Running Terragrunt for logging..."
	cd $(TERRAGRUNT_ROOT)/logging && $(TERRAGRUNT_CMD) 

terragrunt-repository:
	@echo "Running Terragrunt for repository..."
	cd $(TERRAGRUNT_ROOT)/repository && $(TERRAGRUNT_CMD) 

terragrunt-videoserver:
	@echo "Running Terragrunt for videoserver..."
	cd $(TERRAGRUNT_ROOT)/videoserver && $(TERRAGRUNT_CMD) 

terragrunt-client:
	@echo "Running Terragrunt for client..."
	cd $(TERRAGRUNT_ROOT)/client && $(TERRAGRUNT_CMD) 

	






