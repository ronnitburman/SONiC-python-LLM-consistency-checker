"""Deterministic explanation agent — template-based fallback.

Used when no LLM is configured or for fast, offline explanations.
Each finding category maps to a pre-written template that explains
what the mismatch means in plain English.
"""

from __future__ import annotations

from sonic_consistency_checker.ai.models import FindingExplanation
from sonic_consistency_checker.ai.skill_loader import read_skill
from sonic_consistency_checker.core.models import Finding, PortView


def _infer_dbs(finding: Finding) -> list[str]:
    """Infer which DBs are involved from finding category and evidence."""
    cat = finding.category
    mapping = {
        "PORT_MISSING_IN_STATE_DB": ["CONFIG_DB", "STATE_DB"],
        "PORT_ADMIN_UP_OPER_DOWN": ["CONFIG_DB", "STATE_DB", "APPL_DB"],
        "PORT_MTU_MISMATCH": ["CONFIG_DB", "APPL_DB"],
        "PORT_SPEED_MISMATCH": ["CONFIG_DB", "APPL_DB"],
        "PORT_COUNTERS_MISSING": ["COUNTERS_DB"],
        "TRANSCEIVER_INFO_MISSING": ["STATE_DB"],
        "ROUTE_TABLE_DRIFT": ["APPL_DB", "ASIC_DB"],
        "VLAN_MEMBERSHIP_MISMATCH": ["CONFIG_DB", "APPL_DB"],
        "LAG_MEMBER_MISMATCH": ["CONFIG_DB", "APPL_DB"],
    }
    return mapping.get(cat, [d for d in ["CONFIG_DB", "APPL_DB", "STATE_DB", "ASIC_DB", "COUNTERS_DB"] if d in str(finding.evidence)])


_TEMPLATES: dict[str, dict] = {
    "PORT_ADMIN_UP_OPER_DOWN": {
        "title_tpl": "{obj} is configured up but operationally down",
        "plain": "CONFIG_DB says {obj} should be enabled, but the operational state shows it's down. The desired configuration and observed runtime state disagree.",
        "layers": ["Configuration layer", "Runtime state layer", "Platform/transceiver layer", "Physical/optical link layer"],
        "why": "A port that is admin-up but oper-down cannot pass traffic. This is a classic desired-state vs observed-state mismatch — the most common diagnostic pattern in SONiC.",
        "interview": "This finding compares CONFIG_DB desired state against STATE_DB operational state. Admin up means the port is enabled by configuration. Oper down means SONiC does not see link. I would next verify physical connectivity, transceiver presence, remote peer state, and speed/FEC compatibility.",
        "confidence": "The mismatch is deterministic from DB evidence. The root cause requires physical verification.",
    },
    "PORT_MISSING_IN_STATE_DB": {
        "title_tpl": "{obj} exists in config but has no runtime state",
        "plain": "{obj} appears in CONFIG_DB, but no matching runtime port state entry was found in STATE_DB.",
        "layers": ["Configuration layer", "Runtime state layer", "Port/platform service layer"],
        "why": "On real hardware, configured ports usually have runtime state. In virtual SONiC environments, missing state may be expected.",
        "interview": "{obj} exists in CONFIG_DB but STATE_DB has no PORT_TABLE entry. I would check if this is expected in the virtual environment. On real hardware, check portsyncd and platform services.",
        "confidence": "This is a signal, but missing STATE_DB data can be normal in virtual environments.",
    },
    "PORT_MTU_MISMATCH": {
        "title_tpl": "{obj} has an MTU mismatch between CONFIG_DB and APPL_DB",
        "plain": "The configured MTU in CONFIG_DB and the application-level MTU in APPL_DB differ.",
        "layers": ["Configuration layer", "Application intent layer", "SWSS/orchagent processing path"],
        "why": "MTU mismatches can cause packet fragmentation, dropped frames, or configuration propagation issues.",
        "interview": "CONFIG_DB and APPL_DB disagree on MTU. I would check whether config changes are still propagating through SWSS/orchagent, or if there's stale state.",
        "confidence": "The mismatch is deterministic, but timing and propagation delay should be considered.",
    },
    "PORT_SPEED_MISMATCH": {
        "title_tpl": "{obj} has a speed mismatch between CONFIG_DB and APPL_DB",
        "plain": "The configured port speed and the application-level speed differ.",
        "layers": ["Configuration layer", "Application intent layer", "SWSS/orchagent processing path"],
        "why": "Speed mismatches can prevent a port from coming operationally up or cause negotiation failures.",
        "interview": "CONFIG_DB and APPL_DB disagree on speed. I would check if the speed is supported by the platform and transceiver, if FEC/link negotiation constraints apply, and if SWSS processed the change.",
        "confidence": "The DB mismatch is deterministic, but platform/transceiver evidence is needed for root cause.",
    },
    "PORT_COUNTERS_MISSING": {
        "title_tpl": "No direct counters found for {obj}",
        "plain": "The tool did not find direct COUNTERS_DB data for this port. SONiC counters are often indexed by OID rather than port name.",
        "layers": ["Counters/statistics layer", "OID mapping layer"],
        "why": "Counters help verify traffic flow and error rates. Missing counters may be a tool limitation, not a switch problem.",
        "interview": "This does not mean counters are absent — SONiC indexes counters by object ID. The tool's best-effort name matching may not find them. OID mapping would be the next improvement.",
        "confidence": "Soft finding — counter lookup is best-effort in the current tool version.",
    },
    "TRANSCEIVER_INFO_MISSING": {
        "title_tpl": "No transceiver info found for {obj}",
        "plain": "No transceiver information was found in STATE_DB for this port. Expected in SONiC VS or virtual environments.",
        "layers": ["Runtime state layer", "Platform service layer", "Transceiver/optical module layer"],
        "why": "On real optical platforms, transceiver state is critical for debugging presence, signal, and module health.",
        "interview": "No transceiver info in STATE_DB. In virtual SONiC, this is expected. On real hardware, check transceiver presence, platform service health, and DOM sensor publication.",
        "confidence": "Soft finding in virtual environments. Not a hardware issue without real platform evidence.",
    },
    "ROUTE_TABLE_DRIFT": {
        "title_tpl": "Route table drift detected",
        "plain": "The number of routes in APPL_DB ROUTE_TABLE differs from the number of route entries in ASIC_DB. This is the #1 SONiC operational inconsistency.",
        "layers": ["BGP/routing layer", "Orchagent layer", "ASIC programming layer"],
        "why": "Route drift means some routes are in the control plane but not programmed in hardware (black-holed traffic) or vice versa. This is silent — no alarms fire.",
        "interview": "APPL_DB and ASIC_DB route counts differ. This typically happens after warm reboot, orchagent restart, or BGP session flap. I would check orchagent status, BGP peer state, and whether a full reconciliation is needed.",
        "confidence": "Critical finding — route count mismatch is a reliable signal of a real inconsistency.",
    },
    "VLAN_MEMBERSHIP_MISMATCH": {
        "title_tpl": "VLAN membership mismatch for {obj}",
        "plain": "A port's VLAN membership in CONFIG_DB does not match what's in APPL_DB. The port may not be in the VLAN from the switch's perspective.",
        "layers": ["Configuration layer", "VLAN management layer", "vlanmgrd service"],
        "why": "A port not in its expected VLAN means traffic is not being forwarded on the correct broadcast domain — can break L2 connectivity silently.",
        "interview": "CONFIG_DB VLAN_MEMBER and APPL_DB VLAN_MEMBER disagree. I would check if vlanmgrd is running, if the VLAN was recently reconfigured, and if the port is operationally up.",
        "confidence": "The mismatch is deterministic. Verify vlanmgrd service status.",
    },
    "LAG_MEMBER_MISMATCH": {
        "title_tpl": "LAG member mismatch for {obj}",
        "plain": "A port's LAG membership in CONFIG_DB does not match teamd's actual state in APPL_DB.",
        "layers": ["Configuration layer", "LAG/teamd layer", "teamsyncd service"],
        "why": "A mismatched LAG member means the port may not be actively participating in the LAG, reducing bandwidth and resiliency.",
        "interview": "CONFIG_DB PORTCHANNEL members and APPL_DB LAG_TABLE disagree. I would check if teamd is running, if member ports are operationally up, and if teamsyncd has processed the config.",
        "confidence": "The mismatch is deterministic. Verify teamd and member port status.",
    },
}


class DeterministicExplanationAgent:
    """Produces template-based explanations for findings.

    Used as a fallback when no LLM is configured, or for fast
    offline explanations via the API.
    """

    def explain_finding(
        self,
        finding: Finding,
        port_view: PortView | None = None,
    ) -> FindingExplanation:
        cat = finding.category
        tmpl = _TEMPLATES.get(cat)

        if tmpl:
            return FindingExplanation(
                finding_id=finding.id,
                title=tmpl["title_tpl"].format(obj=finding.object_name),
                plain_english_summary=tmpl["plain"].format(obj=finding.object_name),
                dbs_involved=_infer_dbs(finding),
                sonic_layers_involved=tmpl["layers"],
                why_it_matters=tmpl["why"],
                possible_causes=finding.possible_causes,
                suggested_commands=finding.suggested_commands,
                interview_explanation=tmpl["interview"].format(obj=finding.object_name),
                confidence_notes=tmpl["confidence"],
                raw_evidence=finding.evidence,
            )

        # Generic fallback for unknown categories
        return FindingExplanation(
            finding_id=finding.id,
            title=finding.summary,
            plain_english_summary=f"The consistency checker found: {finding.summary}",
            dbs_involved=_infer_dbs(finding),
            sonic_layers_involved=["SONiC DB layer", "Control-plane state layer"],
            why_it_matters="This indicates an area where SONiC databases disagree and should be investigated.",
            possible_causes=finding.possible_causes,
            suggested_commands=finding.suggested_commands,
            interview_explanation=f"I would use the evidence in this finding to identify which SONiC DBs disagree, then inspect the relevant service path and runtime commands.",
            confidence_notes="This is a generic explanation — no category-specific template exists yet.",
            raw_evidence=finding.evidence,
        )

    def explain_port(self, port_view: PortView) -> list[FindingExplanation]:
        return [
            self.explain_finding(f, port_view=port_view)
            for f in port_view.findings
        ]
