
/*
 * DAY 13 — OpenAPI Contract Viewer
 *
 * DEMO SPECIFICATION ONLY.
 * This local sample does not represent a verified backend contract.
 * The viewer reads this object without making network requests.
 */

export const mockOpenApiContract = {
  openapi: "3.0.3",

  info: {
    title: "API Sentinel Demo API",
    version: "1.0.0",
    description:
      "Illustrative API contract for the API Sentinel frontend.",
  },

  servers: [
    {
      url: "https://api.example.invalid",
      description: "Placeholder server; not a real API destination",
    },
  ],

  paths: {
    "/api/v1/users": {
      get: {
        summary: "Retrieve users",
        description:
          "Illustrative operation for retrieving user records.",

        parameters: [
          {
            name: "page",
            in: "query",
            required: false,
            description: "Page number",
            schema: {
              type: "integer",
            },
          },
        ],

        responses: {
          "200": {
            description: "User records returned successfully",
          },
          "401": {
            description: "Authentication required",
          },
        },
      },
    },

    "/api/v1/auth/login": {
      post: {
        summary: "Authenticate a user",
        description: "Illustrative login operation.",

        requestBody: {
          required: true,

          content: {
            "application/json": {
              schema: {
                type: "object",

                properties: {
                  username: {
                    type: "string",
                  },
                  password: {
                    type: "string",
                    format: "password",
                  },
                },

                required: ["username", "password"],
              },
            },
          },
        },

        responses: {
          "200": {
            description: "Authentication successful",
          },
          "401": {
            description: "Authentication failed",
          },
        },
      },
    },

    "/api/v1/products": {
      get: {
        summary: "List products",
        description:
          "Illustrative operation for listing products.",

        responses: {
          "200": {
            description: "Product list returned successfully",
          },
        },
      },
    },
  },
};
