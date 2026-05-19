import { reactive, ref, watch } from 'vue';

function canUseStorage() {
  return typeof window !== 'undefined' && !!window.localStorage;
}

function safeRead(key) {
  if (!canUseStorage()) return null;
  try {
    return window.localStorage.getItem(key);
  } catch (_) {
    return null;
  }
}

function safeWrite(key, value) {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(key, value);
  } catch (_) {
    // ignore storage write errors
  }
}

function safeParseJson(raw, fallback) {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}

export function useTablePresetState(storageKey, defaultValue, allowedValues = []) {
  const validate = (value) => {
    if (!allowedValues.length) return value;
    return allowedValues.includes(value) ? value : defaultValue;
  };

  const initialRaw = safeRead(storageKey);
  const initial = validate(initialRaw || defaultValue);
  const state = ref(initial);

  watch(state, (value) => {
    const normalized = validate(String(value || defaultValue));
    if (state.value !== normalized) {
      state.value = normalized;
      return;
    }
    safeWrite(storageKey, normalized);
  });

  return state;
}

export function useTableFiltersState(storageKey, defaults) {
  const initial = {
    ...defaults,
    ...safeParseJson(safeRead(storageKey), {}),
  };
  const state = reactive(initial);

  watch(state, (value) => {
    safeWrite(storageKey, JSON.stringify(value));
  }, { deep: true });

  const reset = () => {
    Object.keys(defaults).forEach((key) => {
      state[key] = defaults[key];
    });
  };

  return { state, reset };
}
