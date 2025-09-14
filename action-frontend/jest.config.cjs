module.exports = {
  testEnvironment: 'jsdom',
  transform: {
    '^.+\.(ts|tsx)$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js'],
  extensionsToTreatAsEsm: ['.ts', '.tsx'],
  transformIgnorePatterns: ['/node_modules/'],
  setupFiles: ['whatwg-fetch']
};


