from typing import Any, Dict, Iterable, Optional


class SelfCorrector:
    def fix_params(
        self,
        params: Dict[str, Any],
        *,
        analysis: str,
        valid_params: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        fixed_params = dict(params or {})

        if analysis == 'empty_result':
            for key in list(fixed_params.keys()):
                if key in ['top_n', 'limit', 'max_items']:
                    try:
                        current = int(fixed_params[key])
                        fixed_params[key] = max(current, 50)
                    except Exception:
                        fixed_params[key] = 50
                elif key in ['severity', 'status', 'filter']:
                    if fixed_params.get(key) in ['Critical', 'Open']:
                        fixed_params.pop(key, None)

        elif analysis == 'dataset_issue':
            if 'dataset' in fixed_params:
                current = fixed_params['dataset']
                alternatives = ['defects', 'tests'] if current == 'defects' else ['tests', 'defects']
                fixed_params['dataset'] = alternatives[0] if current != alternatives[0] else alternatives[1]

        elif analysis == 'invalid_parameters':
            if valid_params is not None:
                allowed = set(valid_params)
                fixed_params = {key: value for key, value in fixed_params.items() if key in allowed}

        return fixed_params