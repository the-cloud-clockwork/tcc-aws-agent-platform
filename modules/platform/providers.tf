provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.resource_prefix
      ManagedBy   = "terraform"
    }
  }
}

# Cross-region provider for Bedrock model access.
# Primary region (aws_region) hosts infrastructure; bedrock_region hosts
# Bedrock models (e.g. eu-west-1 infra, us-west-2 models).
# Use this alias when creating resources that must exist in the Bedrock region.
provider "aws" {
  alias  = "bedrock"
  region = var.bedrock_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.resource_prefix
      ManagedBy   = "terraform"
    }
  }
}
