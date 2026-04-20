import unittest

from agent.core.context_provider_chain import (
    ContextProviderChain,
    PageContextProvider,
    RequestContextProvider,
    RuntimeConfigProvider,
)


class ContextProviderChainTests(unittest.TestCase):
    def test_chain_applies_request_page_context_and_runtime(self):
        chain = ContextProviderChain(
            providers=[
                RequestContextProvider(),
                PageContextProvider(),
                RuntimeConfigProvider(),
            ]
        )

        context = chain.apply(
            {'primary_dataset': 'defects'},
            request={'question': 'prefetched question', 'execution_mode': 'rule'},
            page_context={'dashboard_type': 'defect', 'selected_team': 'DTSV_China'},
            runtime_config={'mode': 'rule', 'requested_mode': 'rule'},
        )

        self.assertEqual(context['request']['question'], 'prefetched question')
        self.assertEqual(context['page_context']['dashboard_type'], 'defect')
        self.assertEqual(context['dashboard_type'], 'defect')
        self.assertEqual(context['runtime']['mode'], 'rule')

    def test_chain_ignores_missing_optional_payloads(self):
        chain = ContextProviderChain(
            providers=[
                RequestContextProvider(),
                PageContextProvider(),
                RuntimeConfigProvider(),
            ]
        )

        context = chain.apply({'primary_dataset': 'defects'})

        self.assertEqual(context, {'primary_dataset': 'defects'})


if __name__ == '__main__':
    unittest.main()