"""WAF WebACL construct for API Gateway protection."""
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    aws_wafv2 as wafv2,
)


class WafWebAcl(Construct):
    """Creates a WAF WebACL with rate limiting, IP whitelist, and managed rule groups.

    Attach to API Gateway or ALB via web_acl_arn.

    Rules (by priority):
    1. IP whitelist -- allow known IPs (production env only)
    2. Rate limiting -- block IPs exceeding request threshold
    3. AWS Managed Rules: Common Rule Set -- SQL injection, XSS, etc.
    4. AWS Managed Rules: Known Bad Inputs -- Log4j, etc.
    5. Default action: ALLOW
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        rate_limit: int = 1000,
        ip_whitelist: list[str] | None = None,
        resource_prefix: str = "platform",
    ) -> None:
        super().__init__(scope, construct_id)

        self.env_name = env_name
        prefix = resource_prefix
        rules: list[wafv2.CfnWebACL.RuleProperty] = []
        priority = 0

        # -- Rule 1: IP Whitelist (production env only) --------------------------

        if ip_whitelist and env_name == "production":
            # Create IP set for whitelisted addresses
            self.ip_set = wafv2.CfnIPSet(
                self,
                "WhitelistIPSet",
                name=f"{prefix}-{env_name}-whitelist",
                scope="REGIONAL",
                ip_address_version="IPV4",
                addresses=ip_whitelist,
            )

            rules.append(
                wafv2.CfnWebACL.RuleProperty(
                    name="IPWhitelist",
                    priority=priority,
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        allow=wafv2.CfnWebACL.AllowActionProperty(),
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        ip_set_reference_statement=wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                            arn=self.ip_set.attr_arn,
                        ),
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"{prefix}-{env_name}-ip-whitelist",
                        sampled_requests_enabled=True,
                    ),
                )
            )
            priority += 1

        # -- Rule 2: Rate Limiting -----------------------------------------

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="RateLimit",
                priority=priority,
                action=wafv2.CfnWebACL.RuleActionProperty(
                    block=wafv2.CfnWebACL.BlockActionProperty(),
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                        limit=rate_limit,
                        aggregate_key_type="IP",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"{prefix}-{env_name}-rate-limit",
                    sampled_requests_enabled=True,
                ),
            )
        )
        priority += 1

        # -- Rule 3: AWS Managed Rules -- Common Rule Set ------------------

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="AWSManagedRulesCommonRuleSet",
                priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    none={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesCommonRuleSet",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"{prefix}-{env_name}-common-rules",
                    sampled_requests_enabled=True,
                ),
            )
        )
        priority += 1

        # -- Rule 4: AWS Managed Rules -- Known Bad Inputs -----------------

        rules.append(
            wafv2.CfnWebACL.RuleProperty(
                name="AWSManagedRulesKnownBadInputs",
                priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    none={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesKnownBadInputsRuleSet",
                    ),
                ),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"{prefix}-{env_name}-known-bad-inputs",
                    sampled_requests_enabled=True,
                ),
            )
        )

        # -- WebACL --------------------------------------------------------

        self.web_acl = wafv2.CfnWebACL(
            self,
            "WebACL",
            name=f"{prefix}-{env_name}-web-acl",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow=wafv2.CfnWebACL.AllowActionProperty(),
            ),
            rules=rules,
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"{prefix}-{env_name}-web-acl",
                sampled_requests_enabled=True,
            ),
        )

        self.web_acl_arn = self.web_acl.attr_arn
