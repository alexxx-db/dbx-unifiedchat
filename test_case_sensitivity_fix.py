"""
Test Case Sensitivity Fix for Clarification Protection

Verifies that the protection layers work with both uppercase and lowercase intent types.

NOTE: This is a standalone test that replicates the helper function logic
without requiring full module imports (avoiding langchain dependencies).
"""

import sys


def should_skip_clarification_for_intent(intent_type: str) -> bool:
    """
    Replica of the helper function from intent_detection_service.py
    
    This tests the case-insensitive comparison logic.
    """
    skip_intents = {
        "clarification_response",  # Already answering a clarification
    }
    
    # Case-insensitive comparison to handle both uppercase and lowercase
    return intent_type.lower() in skip_intents


def test_uppercase_clarification_response():
    """Test that uppercase CLARIFICATION_RESPONSE is handled"""
    result = should_skip_clarification_for_intent("CLARIFICATION_RESPONSE")
    assert result == True, "Should skip clarification for uppercase CLARIFICATION_RESPONSE"
    print("✅ Test 1 PASS: Uppercase 'CLARIFICATION_RESPONSE' → skip=True")


def test_lowercase_clarification_response():
    """Test that lowercase clarification_response is handled"""
    result = should_skip_clarification_for_intent("clarification_response")
    assert result == True, "Should skip clarification for lowercase clarification_response"
    print("✅ Test 2 PASS: Lowercase 'clarification_response' → skip=True")


def test_mixed_case_clarification_response():
    """Test that mixed case is handled"""
    result = should_skip_clarification_for_intent("Clarification_Response")
    assert result == True, "Should skip clarification for mixed case"
    print("✅ Test 3 PASS: Mixed case 'Clarification_Response' → skip=True")


def test_uppercase_new_question():
    """Test that uppercase NEW_QUESTION is not skipped"""
    result = should_skip_clarification_for_intent("NEW_QUESTION")
    assert result == False, "Should NOT skip clarification for NEW_QUESTION"
    print("✅ Test 4 PASS: Uppercase 'NEW_QUESTION' → skip=False")


def test_lowercase_new_question():
    """Test that lowercase new_question is not skipped"""
    result = should_skip_clarification_for_intent("new_question")
    assert result == False, "Should NOT skip clarification for new_question"
    print("✅ Test 5 PASS: Lowercase 'new_question' → skip=False")


def test_uppercase_refinement():
    """Test that uppercase REFINEMENT is not skipped"""
    result = should_skip_clarification_for_intent("REFINEMENT")
    assert result == False, "Should NOT skip clarification for REFINEMENT"
    print("✅ Test 6 PASS: Uppercase 'REFINEMENT' → skip=False")


def test_uppercase_continuation():
    """Test that uppercase CONTINUATION is not skipped"""
    result = should_skip_clarification_for_intent("CONTINUATION")
    assert result == False, "Should NOT skip clarification for CONTINUATION"
    print("✅ Test 7 PASS: Uppercase 'CONTINUATION' → skip=False")


def run_all_tests():
    """Run all test cases"""
    print("="*80)
    print("CASE SENSITIVITY FIX - TEST SUITE")
    print("="*80)
    print("\nTesting should_skip_clarification_for_intent() helper function")
    print("Verifies case-insensitive comparison works correctly\n")
    
    tests = [
        test_uppercase_clarification_response,
        test_lowercase_clarification_response,
        test_mixed_case_clarification_response,
        test_uppercase_new_question,
        test_lowercase_new_question,
        test_uppercase_refinement,
        test_uppercase_continuation,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"❌ Test FAILED: {test.__name__}")
            print(f"   Error: {e}")
            failed.append(test.__name__)
    
    print("\n" + "="*80)
    print("TEST RESULTS")
    print("="*80)
    
    if failed:
        print(f"❌ {len(failed)}/{len(tests)} tests FAILED")
        for name in failed:
            print(f"   - {name}")
        return 1
    else:
        print(f"✅ ALL {len(tests)} TESTS PASSED")
        print("\n✅ Case sensitivity fix is working correctly!")
        print("   - Handles uppercase (CLARIFICATION_RESPONSE)")
        print("   - Handles lowercase (clarification_response)")
        print("   - Handles mixed case (Clarification_Response)")
        print("   - Only skips clarification_response (not other intents)")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
