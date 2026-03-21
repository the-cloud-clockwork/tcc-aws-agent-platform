## -----------------------------------------------------
## Workflows Module
## Reads workflow YAML blueprints and creates
## Step Functions state machines with EventBridge triggers.
##
## Usage:
##   module "workflows" {
##     source       = "git::repo.git//modules/workflows"
##     workflow_dir = "./blueprints/workflows"
##     agent_runtime_arns = module.agents.runtime_arns
##     ...
##   }
## -----------------------------------------------------
