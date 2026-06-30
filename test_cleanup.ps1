# Test cleanup script
cd c:\100_Projects\as-docs\tests

Write-Host "Deleting obsolete phase test files..."
git rm -f test_phase1.py test_phase2_cli.py test_phase3_mcp_server.py test_phase4_cli.py test_phase5_template_integration.py

Write-Host "`nRenaming 'phase2' prefix tests to core test names..."
git mv test_phase2_cache.py test_enrichment_cache.py
git mv test_phase2_config.py test_core_config.py
git mv test_phase2_copilot_auth.py test_copilot_auth.py
git mv test_phase2_enrichment.py test_enrichment.py
git mv test_phase2_providers.py test_ai_providers.py

Write-Host "`nRenaming remaining phase tests..."
git mv test_phase2_7_integration_validation.py test_integration_validation.py
git mv test_phase6_flow_pipeline.py test_flow_pipeline.py
git mv test_phase7_packaging.py test_packaging.py

Write-Host "`nFinal test file listing:"
Get-ChildItem test_*.py -File -Name | Sort-Object

Write-Host "`nGit status:"
git status --short tests/
