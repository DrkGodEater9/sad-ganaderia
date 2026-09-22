import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

export default [
  // resources/ es material de referencia del dueno del proyecto (incluye un
  // script suelto para el editor web de Earth Engine, con sus propios
  // globals `ee`/`Export`): no es parte del codigo de esta app.
  { ignores: ["dist/", "node_modules/", "resources/"] },
  js.configs.recommended,
  {
    // La app React/Vite (dibujar potreros).
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.es2021 },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "no-unused-vars": ["warn", { varsIgnorePattern: "^_", argsIgnorePattern: "^_" }],
    },
  },
];
