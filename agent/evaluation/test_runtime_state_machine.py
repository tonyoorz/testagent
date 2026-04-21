import unittest

from agent.core.runtime_state_machine import RuntimeStateMachine


class RuntimeStateMachineTests(unittest.TestCase):
    def test_allows_forward_transition(self):
        machine = RuntimeStateMachine()

        state = machine.initialize()
        updated = machine.transition(state, 'guarded')

        self.assertEqual(updated['runtime_stage'], 'guarded')

    def test_rejects_invalid_transition(self):
        machine = RuntimeStateMachine()

        state = machine.initialize()

        with self.assertRaises(ValueError):
            machine.transition(state, 'completed')


if __name__ == '__main__':
    unittest.main()