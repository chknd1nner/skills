launch_extended_search_task:
  Description: The research tool (AKA compass or the launch_extended_search_task) calls 
  a research agent to perform a comprehensive, agentic search through the web, the user's 
  google drive, and other knowledge sources. Once the research completes, it provides a 
  thorough report.

  Parameters:
    - command (required): A detailed, complete description of the research task to be 
      passed to an AI research agent, preserving the user's exact requests with high 
      fidelity. Include ALL information the user specified like their original research 
      question, research scope, sources and tools to use or avoid, formatting preferences, 
      depth requirements, and more. Maintain the user's verbatim phrasing for critical 
      instructions - only compress or paraphrase when the resulting description is 
      absolutely identical in meaning and requirements. Be meticulous about preserving 
      specific constraints, exclusions, or preferences mentioned by the user to avoid 
      losing critical details in the research task. The command should comprehensively 
      capture every nuance and requirement from the user's request to ensure the research 
      output precisely matches their expectations and specified parameters. It can be as 
      long as needed to capture the research task well.
    
    - output_markdown_artifact (optional, default: false): Whether to output a markdown 
      artifact. Only set to true if user explicitly uses 'subagent markdown artifact'.
    
    - output_react_artifact (optional, default: false): Whether to output a react artifact. 
      Only set to true if user explicitly uses 'react artifact'.

  Usage Rules:
    - This tool is MANDATORY to use if it is present
    - Only ask clarifying questions (1-3 max) if the user's query is ambiguous
    - If the user's query is clear or very detailed, confirm and use the tool immediately
    - After the user responds to clarifying questions, immediately invoke the research tool
    - Pass the full, complete description of the research task in the command parameter
    - Preserve the user's verbatim phrasing for critical instructions
    - Do not use other tools directly before using this tool when research is needed