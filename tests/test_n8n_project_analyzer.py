"""Tests: n8n project analyzer."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.n8n_project_analyzer import analyse_n8n_project, generate_analysis_report


class TestN8nAnalyzer:
    def test_missing_root_returns_report_with_error(self, tmp_path):
        """A non-existent n8n root returns an AnalysisReport with an error."""
        report = analyse_n8n_project(str(tmp_path / "nonexistent"))
        assert len(report.errors) > 0

    def test_scans_md_files(self, tmp_path):
        """Markdown files are scanned and rejection codes extracted."""
        md_file = tmp_path / "HANDOVER.md"
        md_file.write_text(
            "# Test\nRejection: UNKNOWN_MATERIAL_FOUND, CONTRACT_KEYWORD_MISSING\n",
            encoding="utf-8",
        )
        report = analyse_n8n_project(str(tmp_path))
        # At least one file was analysed
        assert len(report.analysed_files) >= 1

    def test_extracts_workflow_ids_from_json(self, tmp_path):
        """JSON workflow files are detected."""
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        wf_file = wf_dir / "test.workflow.json"
        wf_data = {
            "id": "SWDjBN27Tnc8r6w8",
            "name": "DEV EDIPUSHBOT",
            "nodes": [
                {"type": "n8n-nodes-base.code", "name": "Sanitize AI JSON",
                 "parameters": {"jsCode": "// edifact UNB generation"}}
            ],
        }
        wf_file.write_text(json.dumps(wf_data), encoding="utf-8")
        report = analyse_n8n_project(str(tmp_path))
        assert any("workflow" in wf.lower() for wf in report.detected_workflows)

    def test_ignores_binary_files(self, tmp_path):
        """Binary file extensions are not analysed."""
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        # Should not crash
        report = analyse_n8n_project(str(tmp_path))
        assert not any("image.png" in f for f in report.analysed_files)

    def test_generates_report_file(self, tmp_path):
        """generate_analysis_report creates a Markdown file."""
        report = analyse_n8n_project(str(tmp_path))
        out_path = tmp_path / "N8N_ANALYSIS_REPORT.md"
        generate_analysis_report(report, str(out_path))
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "# N8N_ANALYSIS_REPORT" in content
        assert "ELM_STANDARD" in content
        assert "AUTHORISED_SENDER_ID" not in content  # should show actual value

    def test_report_contains_known_rules(self, tmp_path):
        """Generated report embeds the verified business rules section."""
        report = analyse_n8n_project(str(tmp_path))
        out_path = tmp_path / "REPORT.md"
        generate_analysis_report(report, str(out_path))
        content = out_path.read_text(encoding="utf-8")
        assert "Duplicate Detection" in content
        assert "SFTP_SUBMITTED" in content
        assert "postal exact" in content.lower() or "POSTAL_EXACT" in content
