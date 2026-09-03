// Vitest setup — runs once before the test suite. Registers jest-dom's
// custom matchers (toBeInTheDocument, toHaveAttribute, ...) globally so
// individual test files don't each need to import them.
import '@testing-library/jest-dom/vitest';
