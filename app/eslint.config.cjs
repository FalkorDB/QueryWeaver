// ESLint v9 flat config equivalent for the project's TypeScript rules
module.exports = [
	{
		ignores: ['**/node_modules/**', 'dist/**'],
	},
		{
			languageOptions: {
				parser: require('@typescript-eslint/parser'),
				parserOptions: {
					ecmaVersion: 2020,
					sourceType: 'module',
				},
			},
		},
		{
			plugins: {
				'@typescript-eslint': require('@typescript-eslint/eslint-plugin'),
			},
		},
	{
		rules: {
			// Base JS recommended rules
			'no-unused-vars': ['warn', { 
				'argsIgnorePattern': '^_',
				'varsIgnorePattern': '^_'
			}],
			// TypeScript rules
			'@typescript-eslint/no-explicit-any': 'off',
		},
		linterOptions: {
			reportUnusedDisableDirectives: true,
		},
	},
];
